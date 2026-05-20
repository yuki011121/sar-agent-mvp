#!/usr/bin/env python3
"""
Command Agent - FastAPI HTTP server (v3)

POST /query → SSE stream (agent_start, agent_result, path_data, final, done)

Replaces the old Redis consumer loop with a direct HTTP + SSE architecture.
Session history is managed by LangGraph MemorySaver inside graph.py.
"""

import os
import sys
import logging
import uuid
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from .graph import run_query_stream, run_query, get_session_history

HTTP_PORT = int(os.getenv("COMMAND_AGENT_HTTP_PORT", "8008"))
AGENT_NAME = "command-agent"
AGENT_VERSION = "command-agent-v3.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(AGENT_NAME)


# ─── FastAPI app ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"{AGENT_NAME} {AGENT_VERSION} starting on port {HTTP_PORT}")
    yield
    logger.info(f"{AGENT_NAME} shutting down")


app = FastAPI(title="SAR Command Agent", version="3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    file_urls: Optional[List[Dict[str, Any]]] = None


@app.post("/query")
async def handle_query(req: QueryRequest):
    """SSE stream: agent_start → agent_result → [path_data] → final → done."""
    session_id = req.session_id or str(uuid.uuid4())
    logger.info(f"Query received — session={session_id[:8]} query={req.query[:80]}")
    return StreamingResponse(
        run_query_stream(req.query, session_id, req.file_urls),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/session/{session_id}/history")
async def session_history(session_id: str):
    return {"session_id": session_id, "history": get_session_history(session_id)}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": AGENT_NAME, "version": AGENT_VERSION}


@app.get("/.well-known/agent.json")
async def agent_card():
    return JSONResponse({
        "name": AGENT_NAME,
        "description": "SAR Command Agent — orchestrates specialist agents for search and rescue.",
        "version": AGENT_VERSION,
        "url": f"http://{AGENT_NAME}:{HTTP_PORT}",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "skills": [{"id": "query", "name": "SAR Query",
                    "inputModes": ["application/json"],
                    "outputModes": ["text/event-stream"]}],
    })


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="SAR Command Agent")
    parser.add_argument(
        "--mode", choices=["service", "interactive", "query"],
        default="service",
        help="service: HTTP server (default); interactive: CLI; query: single query",
    )
    parser.add_argument("--query", "-q", type=str, help="Query text (query mode)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(f"{AGENT_NAME} {AGENT_VERSION}")
    logger.info("=" * 60)

    if args.mode == "service":
        logger.info(f"Starting HTTP service on port {HTTP_PORT}")
        uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")

    elif args.mode == "query":
        if not args.query:
            print("Error: --query required in query mode")
            sys.exit(1)
        response = run_query(args.query, verbose=args.verbose)
        print(f"\nResponse:\n{response}")

    elif args.mode == "interactive":
        session_id = str(uuid.uuid4())
        print(f"\nInteractive mode — session: {session_id[:8]}...")
        print("Type 'new' for a new session, 'exit' to quit.\n")
        while True:
            try:
                text = input("You: ").strip()
                if not text:
                    continue
                if text.lower() in ("exit", "quit"):
                    break
                if text.lower() == "new":
                    session_id = str(uuid.uuid4())
                    print(f"\nNew session: {session_id[:8]}...\n")
                    continue
                print("\nProcessing...\n")
                response = run_query(text, session_id=session_id)
                print(f"Assistant: {response}\n")
            except (KeyboardInterrupt, EOFError):
                break


if __name__ == "__main__":
    main()
