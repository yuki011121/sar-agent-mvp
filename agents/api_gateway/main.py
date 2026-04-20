#!/usr/bin/env python3
"""
API Gateway for SAR Multi-Agent System

Provides HTTP REST and WebSocket interfaces for external clients to interact
with the SAR system. This is the main entry point for:
- Frontend applications
- External integrations
- Testing and debugging

Endpoints:
- POST /missions       - Create a new SAR mission
- GET  /missions/{id}  - Get mission status
- POST /query          - Send a query to Command Agent
- POST /upload         - Upload files to MinIO storage
- POST /upload/analyze - Upload files and dispatch for analysis
- GET  /status         - Get system status
- GET  /analysis       - Get latest ClueMeister analysis
- GET  /streams/{name} - Get latest data from any stream
- WS   /ws             - WebSocket for real-time updates
"""

import os
import json
import asyncio
import logging
import uuid
import io
from typing import Optional, Dict, Any, List, AsyncGenerator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    logger = logging.getLogger("api-gateway")
    logger.warning("MinIO client not available. File upload will be disabled.")

from shared import RedisBus, wrap_envelope, parse_message_from_stream

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = "api-gateway"
AGENT_VERSION = "api-gateway-v1.0"
HOST = os.getenv("API_HOST", "0.0.0.0")
PORT = int(os.getenv("API_PORT", "8080"))

# Streams
MISSION_STREAM = "mission.new"
QUERY_STREAM = "command.query.raw"
RESPONSE_STREAM = "command.response.raw"
ANALYSIS_STREAM = "cluemeister.analysis.raw"
PHOTO_TASK_STREAM = "photo.task.raw"
INTERVIEW_INPUT_STREAM = "interview.in.raw"

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "sar-files")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


# ============================================================================
# Redis Connection
# ============================================================================

redis_client: Optional[redis.Redis] = None
bus: Optional[RedisBus] = None


def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
    return redis_client


def get_bus() -> RedisBus:
    global bus
    if bus is None:
        bus = RedisBus(REDIS_URL)
    return bus


# ============================================================================
# MinIO Connection
# ============================================================================

minio_client: Optional[Any] = None


def get_minio() -> Optional[Any]:
    """Get or create MinIO client. Returns None if MinIO is not available."""
    global minio_client
    if not MINIO_AVAILABLE:
        return None
    if minio_client is None:
        try:
            minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE
            )
            # Ensure bucket exists
            if not minio_client.bucket_exists(MINIO_BUCKET):
                minio_client.make_bucket(MINIO_BUCKET)
                logger.info(f"Created MinIO bucket: {MINIO_BUCKET}")
            logger.info(f"Connected to MinIO at {MINIO_ENDPOINT}")
        except Exception as e:
            logger.error(f"Failed to connect to MinIO: {e}")
            return None
    return minio_client


def upload_to_minio(file_data: bytes, filename: str, content_type: str, mission_id: str = None) -> Optional[str]:
    """
    Upload a file to MinIO and return its URL.
    
    Args:
        file_data: File content as bytes
        filename: Original filename
        content_type: MIME type
        mission_id: Optional mission ID for organizing files
        
    Returns:
        Presigned URL for accessing the file, or None on error
    """
    client = get_minio()
    if not client:
        return None
    
    try:
        # Generate object path
        if mission_id:
            object_name = f"missions/{mission_id}/files/{filename}"
        else:
            object_name = f"uploads/{datetime.utcnow().strftime('%Y%m%d')}/{filename}"
        
        # Upload file
        client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(file_data),
            length=len(file_data),
            content_type=content_type
        )
        
        # Generate presigned URL (valid for 7 days)
        url = client.presigned_get_object(
            MINIO_BUCKET,
            object_name,
            expires=timedelta(days=7)
        )
        
        logger.info(f"Uploaded file to MinIO: {object_name}")
        return url
        
    except S3Error as e:
        logger.error(f"MinIO upload error: {e}")
        return None
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return None


# ============================================================================
# Pydantic Models
# ============================================================================

class PersonInfo(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    health_conditions: Optional[List[str]] = []
    medications: Optional[List[str]] = []
    clothing: Optional[str] = None
    last_seen: Optional[Dict[str, Any]] = None


class LocationInfo(BaseModel):
    name: Optional[str] = None
    terrain: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None
    search_radius_km: Optional[float] = 5.0


class MissionCreate(BaseModel):
    """Request body for creating a new mission."""
    type: str = Field(default="missing_person", description="Mission type")
    priority: str = Field(default="high", description="Priority level")
    person: PersonInfo
    location: Optional[LocationInfo] = None
    witnesses: Optional[List[Dict[str, str]]] = []
    interview_notes: Optional[str] = None


class MissionResponse(BaseModel):
    """Response after creating a mission."""
    id: str
    status: str
    message: str
    timestamp: str


class QueryRequest(BaseModel):
    """Request body for sending a query."""
    question: str = Field(..., description="The question to ask")
    session_id: Optional[str] = Field(default=None, description="Session ID for multi-turn conversations")
    timeout: Optional[int] = Field(default=120, description="Timeout in seconds")


class QueryResponse(BaseModel):
    """Response from a query."""
    query_id: str
    session_id: str
    question: str
    response: str
    timestamp: str


class SystemStatus(BaseModel):
    """System status response."""
    status: str
    agents: Dict[str, Any]
    streams: Dict[str, int]
    timestamp: str


# ============================================================================
# WebSocket Manager
# ============================================================================

class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")


manager = ConnectionManager()


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"Starting {AGENT_NAME} {AGENT_VERSION}")
    get_redis()  # Initialize connection
    get_bus()
    logger.info(f"Connected to Redis at {REDIS_URL}")
    yield
    # Shutdown
    logger.info("Shutting down API Gateway")


app = FastAPI(
    title="SAR Multi-Agent System API",
    description="API Gateway for Search and Rescue Multi-Agent System",
    version=AGENT_VERSION,
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================

def read_stream_latest(stream_name: str, count: int = 1) -> List[Dict]:
    """Read latest messages from a stream."""
    client = get_redis()
    messages = client.xrevrange(stream_name, count=count)
    
    results = []
    for msg_id, data in messages:
        try:
            parsed = parse_message_from_stream(data)
            if parsed and hasattr(parsed, 'payload'):
                results.append({"id": msg_id, "data": parsed.payload})
            elif isinstance(parsed, dict):
                results.append({"id": msg_id, "data": parsed.get('payload', parsed)})
        except:
            results.append({"id": msg_id, "data": data})
    
    return results


def wait_for_response(query_id: str, timeout: int = 60) -> Optional[Dict]:
    """Wait for a response to a specific query."""
    client = get_redis()
    start_time = datetime.now()
    last_id = "0"
    
    while (datetime.now() - start_time).total_seconds() < timeout:
        messages = client.xread({RESPONSE_STREAM: last_id}, count=10, block=1000)
        
        if messages:
            for stream_name, stream_messages in messages:
                for msg_id, data in stream_messages:
                    last_id = msg_id
                    try:
                        parsed = parse_message_from_stream(data)
                        payload = parsed.payload if hasattr(parsed, 'payload') else parsed
                        
                        if isinstance(payload, dict):
                            if payload.get('query_id') == query_id:
                                return payload
                    except:
                        pass
    
    return None


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": AGENT_NAME, "version": AGENT_VERSION}


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check."""
    try:
        get_redis().ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")


@app.post("/missions", response_model=MissionResponse, tags=["Missions"])
async def create_mission(mission: MissionCreate):
    """
    Create a new SAR mission.
    
    This will:
    1. Generate a unique mission ID
    2. Publish the mission to mission.new stream
    3. Mission Controller will route to appropriate agents
    """
    mission_id = f"MISSION-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    payload = {
        "id": mission_id,
        "type": mission.type,
        "priority": mission.priority,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "person": mission.person.model_dump(),
        "location": mission.location.model_dump() if mission.location else {},
        "witnesses": mission.witnesses,
        "interview_notes": mission.interview_notes,
    }
    
    try:
        message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=MISSION_STREAM
        )
        get_bus().publish(message)
        
        logger.info(f"Mission created: {mission_id}")
        
        # Broadcast to WebSocket clients
        await manager.broadcast({
            "event": "mission_created",
            "data": payload
        })
        
        return MissionResponse(
            id=mission_id,
            status="created",
            message="Mission created and routed to agents",
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        logger.error(f"Error creating mission: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/missions/{mission_id}", tags=["Missions"])
async def get_mission_status(mission_id: str):
    """
    Get the status of a mission.
    
    Note: This is a simplified implementation. In production,
    you would track mission state in a database.
    """
    # Check various streams for mission-related data
    status = {
        "mission_id": mission_id,
        "status": "processing",
        "agents_responded": [],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    
    # Check each agent's output for this mission
    streams_to_check = [
        ("health.assessment.raw", "health"),
        ("history.out.raw", "history"),
        ("interview.analysis.raw", "interview"),
        ("cluemeister.analysis.raw", "cluemeister"),
    ]
    
    client = get_redis()
    for stream, agent in streams_to_check:
        try:
            messages = client.xrevrange(stream, count=10)
            for msg_id, data in messages:
                parsed = parse_message_from_stream(data)
                payload = parsed.payload if hasattr(parsed, 'payload') else parsed
                if isinstance(payload, dict) and payload.get('mission_id') == mission_id:
                    status["agents_responded"].append(agent)
                    break
        except:
            pass
    
    return status


@app.post("/query", response_model=QueryResponse, tags=["Query"])
async def send_query(request: QueryRequest):
    """
    Send a query to the Command Agent.
    
    This will:
    1. Publish the query to command.query.raw
    2. Wait for response on command.response.raw
    3. Return the response
    
    Use session_id for multi-turn conversations. If not provided,
    a new session will be created.
    """
    import uuid as uuid_module
    
    query_id = f"QUERY-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    session_id = request.session_id or str(uuid_module.uuid4())
    
    payload = {
        "id": query_id,
        "query": request.question,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    try:
        # Publish query
        message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=QUERY_STREAM
        )
        get_bus().publish(message)
        
        logger.info(f"Query sent: {query_id} (session: {session_id[:8]}...)")
        
        # Wait for response
        response = wait_for_response(query_id, timeout=request.timeout)
        
        if response:
            return QueryResponse(
                query_id=query_id,
                session_id=session_id,
                question=request.question,
                response=response.get('response', 'No response content'),
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
        else:
            raise HTTPException(
                status_code=504,
                detail="Timeout waiting for response from Command Agent"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", tags=["Chat"])
async def chat(
    message: str = Form(...),
    session_id: str = Form(...),
    files: List[UploadFile] = File(default=[]),
):
    """
    SSE streaming chat endpoint for the frontend.

    Accepts FormData: message (str), session_id (str), files[] (optional).
    Returns text/event-stream with events: agent_start, agent_result, final, done, error.
    """
    query_id = f"QUERY-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    file_urls: List[Dict[str, str]] = []

    # Upload files and pre-dispatch to typed agents
    for file in files:
        content = await file.read()
        url = upload_to_minio(
            file_data=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
        )
        if not url:
            continue
        ext = os.path.splitext(file.filename.lower())[1]
        ftype = (
            "image" if (ext in IMAGE_EXTS or (file.content_type or "").startswith("image/"))
            else "pdf" if ext == ".pdf"
            else "other"
        )
        file_urls.append({"url": url, "filename": file.filename, "type": ftype})

        task_id = f"TASK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        if ftype == "image":
            msg = wrap_envelope(
                payload={"task_id": task_id, "image_url": url, "filename": file.filename},
                source_name=AGENT_NAME, source_version=AGENT_VERSION,
                target_stream=PHOTO_TASK_STREAM,
            )
            get_bus().publish(msg)
            logger.info(f"Pre-dispatched image to photo agent: {task_id}")
        elif ftype == "pdf":
            msg = wrap_envelope(
                payload={"task_id": task_id, "file_url": url, "filename": file.filename},
                source_name=AGENT_NAME, source_version=AGENT_VERSION,
                target_stream=INTERVIEW_INPUT_STREAM,
            )
            get_bus().publish(msg)
            logger.info(f"Pre-dispatched PDF to interview agent: {task_id}")

    # Publish query to command agent, carrying file_urls as context
    cmd_msg = wrap_envelope(
        payload={
            "id": query_id,
            "query": message,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "file_urls": file_urls,
        },
        source_name=AGENT_NAME,
        source_version=AGENT_VERSION,
        target_stream=QUERY_STREAM,
    )
    get_bus().publish(cmd_msg)
    logger.info(f"Chat query published: {query_id}")

    async def event_stream() -> AsyncGenerator[str, None]:
        # Emit agent_start hints for all specialists
        for name in ["weather", "health", "history", "photo", "path", "interview"]:
            yield f"event: agent_start\ndata: {name}\n\n"
            await manager.broadcast({"event": "agent_update", "agent": name})
            await asyncio.sleep(0.03)

        # Capture stream tip AFTER publishing to avoid replaying old messages
        client = get_redis()
        try:
            tip = client.xrevrange(RESPONSE_STREAM, count=1)
            last_id = tip[0][0] if tip else "0-0"
        except Exception:
            last_id = "0-0"

        timeout = 120
        start = asyncio.get_event_loop().time()
        found = False

        while (asyncio.get_event_loop().time() - start) < timeout:
            # block=0: non-blocking, returns immediately if no data
            messages = client.xread({RESPONSE_STREAM: last_id}, count=5, block=0)
            if messages:
                for _, stream_msgs in messages:
                    for msg_id, data in stream_msgs:
                        last_id = msg_id
                        try:
                            parsed = parse_message_from_stream(data)
                            payload = parsed.payload if hasattr(parsed, "payload") else {}
                            if payload.get("query_id") == query_id:
                                for agent in payload.get("agents_used", []):
                                    yield f"event: agent_result\ndata: **{agent}** contributed analysis\n\n"
                                resp = payload.get("response", "")
                                safe_resp = resp.replace("\n", "\ndata: ")
                                yield f"event: final\ndata: {safe_resp}\n\n"
                                yield f"event: done\ndata: {session_id}\n\n"
                                found = True
                        except Exception:
                            pass
                if found:
                    return
            await asyncio.sleep(0.5)

        if not found:
            yield f"event: error\ndata: Timeout: agents did not respond within 120s\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/status", response_model=SystemStatus, tags=["Status"])
async def get_system_status():
    """
    Get overall system status including all agents and streams.
    """
    client = get_redis()
    
    # Check stream lengths
    streams = [
        "weather.forecast.raw",
        "health.assessment.raw",
        "history.out.raw",
        "logistics.requests.raw",
        "path.analysis.raw",
        "photo.analysis.raw",
        "interview.analysis.raw",
        "cluemeister.analysis.raw",
        "command.query.raw",
        "command.response.raw",
        "mission.new",
    ]
    
    stream_counts = {}
    for stream in streams:
        try:
            stream_counts[stream] = client.xlen(stream)
        except:
            stream_counts[stream] = -1  # Error
    
    # Determine agent status based on recent messages
    agents = {}
    agent_streams = {
        "weather": "weather.forecast.raw",
        "health": "health.assessment.raw",
        "history": "history.out.raw",
        "logistics": "logistics.requests.raw",
        "path": "path.analysis.raw",
        "photo": "photo.analysis.raw",
        "interview": "interview.analysis.raw",
        "cluemeister": "cluemeister.analysis.raw",
        "command": "command.response.raw",
    }
    
    for agent, stream in agent_streams.items():
        try:
            messages = client.xrevrange(stream, count=1)
            if messages:
                msg_id, _ = messages[0]
                # Extract timestamp from message ID (format: timestamp-sequence)
                ts = int(msg_id.split('-')[0]) / 1000
                last_update = datetime.fromtimestamp(ts).isoformat()
                agents[agent] = {"status": "active", "last_update": last_update}
            else:
                agents[agent] = {"status": "no_data", "last_update": None}
        except:
            agents[agent] = {"status": "error", "last_update": None}
    
    return SystemStatus(
        status="operational",
        agents=agents,
        streams=stream_counts,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@app.get("/analysis", tags=["Analysis"])
async def get_latest_analysis(count: int = Query(default=1, le=10)):
    """
    Get the latest analysis from ClueMeister.
    """
    results = read_stream_latest(ANALYSIS_STREAM, count=count)
    if not results:
        raise HTTPException(status_code=404, detail="No analysis available")
    return {"analyses": results}


# ============================================================================
# File Upload Endpoints
# ============================================================================

class UploadResponse(BaseModel):
    """Response after uploading files."""
    files: List[Dict[str, str]]
    mission_id: Optional[str]
    message: str


class AnalyzeResponse(BaseModel):
    """Response after uploading and dispatching for analysis."""
    files: List[Dict[str, str]]
    tasks: List[Dict[str, str]]
    mission_id: Optional[str]
    session_id: Optional[str]
    message: str


@app.post("/upload", response_model=UploadResponse, tags=["Files"])
async def upload_files(
    files: List[UploadFile] = File(...),
    mission_id: Optional[str] = Form(default=None)
):
    """
    Upload files to MinIO storage.
    
    Files are stored at: missions/{mission_id}/files/{filename}
    Returns presigned URLs valid for 7 days.
    """
    if not MINIO_AVAILABLE:
        raise HTTPException(status_code=503, detail="File upload service not available")
    
    uploaded = []
    for file in files:
        content = await file.read()
        url = upload_to_minio(
            file_data=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            mission_id=mission_id
        )
        
        if url:
            uploaded.append({
                "filename": file.filename,
                "content_type": file.content_type,
                "size": len(content),
                "url": url
            })
        else:
            logger.error(f"Failed to upload file: {file.filename}")
    
    if not uploaded:
        raise HTTPException(status_code=500, detail="Failed to upload any files")
    
    return UploadResponse(
        files=uploaded,
        mission_id=mission_id,
        message=f"Successfully uploaded {len(uploaded)} file(s)"
    )


@app.post("/upload/analyze", response_model=AnalyzeResponse, tags=["Files"])
async def upload_and_analyze(
    files: List[UploadFile] = File(...),
    mission_id: Optional[str] = Form(default=None),
    session_id: Optional[str] = Form(default=None)
):
    """
    Upload files and automatically dispatch them for analysis.
    
    - Images (jpg, png, gif, webp) → Photo Analysis Agent
    - PDFs → Interview Analysis Agent
    
    Returns task IDs for tracking analysis progress.
    """
    if not MINIO_AVAILABLE:
        raise HTTPException(status_code=503, detail="File upload service not available")
    
    uploaded = []
    tasks = []
    
    # Image extensions
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    
    for file in files:
        content = await file.read()
        url = upload_to_minio(
            file_data=content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            mission_id=mission_id
        )
        
        if not url:
            logger.error(f"Failed to upload file: {file.filename}")
            continue
        
        uploaded.append({
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "url": url
        })
        
        # Determine file type and dispatch to appropriate agent
        filename_lower = file.filename.lower()
        ext = os.path.splitext(filename_lower)[1]
        
        task_id = f"TASK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        if ext in image_extensions or (file.content_type and file.content_type.startswith("image/")):
            # Dispatch to Photo Analysis Agent
            payload = {
                "task_id": task_id,
                "image_url": url,
                "filename": file.filename,
                "mission_id": mission_id,
                "session_id": session_id,
                "submitted_at": datetime.utcnow().isoformat() + "Z",
            }
            
            message = wrap_envelope(
                payload=payload,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=PHOTO_TASK_STREAM
            )
            get_bus().publish(message)
            
            tasks.append({
                "task_id": task_id,
                "filename": file.filename,
                "agent": "photo-analysis",
                "stream": PHOTO_TASK_STREAM
            })
            logger.info(f"Dispatched image for analysis: {task_id}")
            
        elif ext == ".pdf" or file.content_type == "application/pdf":
            # Dispatch to Interview Agent
            payload = {
                "task_id": task_id,
                "file_url": url,
                "filename": file.filename,
                "mission_id": mission_id,
                "session_id": session_id,
                "submitted_at": datetime.utcnow().isoformat() + "Z",
            }
            
            message = wrap_envelope(
                payload=payload,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=INTERVIEW_INPUT_STREAM
            )
            get_bus().publish(message)
            
            tasks.append({
                "task_id": task_id,
                "filename": file.filename,
                "agent": "interview",
                "stream": INTERVIEW_INPUT_STREAM
            })
            logger.info(f"Dispatched PDF for analysis: {task_id}")
        else:
            logger.warning(f"Unknown file type, not dispatched: {file.filename}")
    
    if not uploaded:
        raise HTTPException(status_code=500, detail="Failed to upload any files")
    
    return AnalyzeResponse(
        files=uploaded,
        tasks=tasks,
        mission_id=mission_id,
        session_id=session_id,
        message=f"Uploaded {len(uploaded)} file(s), dispatched {len(tasks)} task(s)"
    )


@app.get("/streams/{stream_name}", tags=["Streams"])
async def get_stream_data(
    stream_name: str,
    count: int = Query(default=5, le=50)
):
    """
    Get latest data from any Redis stream.
    
    Useful for debugging and monitoring.
    """
    # Validate stream name for security
    allowed_streams = [
        "weather.forecast.raw",
        "health.assessment.raw",
        "history.out.raw",
        "history.in.raw",
        "logistics.requests.raw",
        "path.analysis.raw",
        "photo.analysis.raw",
        "interview.analysis.raw",
        "interview.in.raw",
        "cluemeister.analysis.raw",
        "command.query.raw",
        "command.response.raw",
        "mission.new",
        "field.observation.raw",
    ]
    
    if stream_name not in allowed_streams:
        raise HTTPException(status_code=400, detail=f"Stream not allowed: {stream_name}")
    
    results = read_stream_latest(stream_name, count=count)
    return {"stream": stream_name, "count": len(results), "messages": results}


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Clients can subscribe to receive:
    - Mission updates
    - Query responses
    - Agent status changes
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            
            # Echo back or handle commands
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "subscribe":
                    # Future: implement stream subscriptions
                    await websocket.send_json({"type": "subscribed", "streams": message.get("streams", [])})
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================================
# Main
# ============================================================================

def main():
    """Run the API server."""
    import uvicorn
    
    logger.info(f"Starting API Gateway on {HOST}:{PORT}")
    uvicorn.run(
        "agents.api_gateway.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
