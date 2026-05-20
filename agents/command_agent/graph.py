#!/usr/bin/env python3
"""
SAR Command Agent - LangGraph create_react_agent with HTTP specialist tools.

Replaces the old StateGraph + TaskTracker + Redis dispatch approach.
Session history is managed by LangGraph MemorySaver (thread_id = session_id).
"""

import os
import json
import logging
import uuid
from contextvars import ContextVar
from typing import Optional, List, Dict, Any, AsyncGenerator

import httpx
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger("command-agent-graph")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("COMMAND_AGENT_MODEL", "gemini-2.5-flash")
TEMPERATURE = float(os.getenv("COMMAND_AGENT_TEMPERATURE", "0.7"))

DEFAULT_LAT = 35.2828
DEFAULT_LON = -120.6596

AGENT_URLS = {
    "weather":   os.getenv("WEATHER_AGENT_URL",   "http://weather-agent:8001"),
    "health":    os.getenv("HEALTH_AGENT_URL",     "http://health-agent:8002"),
    "path":      os.getenv("PATH_AGENT_URL",       "http://path-analysis-agent:8003"),
    "history":   os.getenv("HISTORY_AGENT_URL",    "http://history-agent:8004"),
    "interview": os.getenv("INTERVIEW_AGENT_URL",  "http://interview-agent:8005"),
    "photo":     os.getenv("PHOTO_AGENT_URL",      "http://photo-agent:8006"),
}

_CURRENT_SESSION_ID: ContextVar[str] = ContextVar("current_session_id", default="")
_CURRENT_TURN_ID: ContextVar[str] = ContextVar("current_turn_id", default="")


def _correlation_payload() -> Dict[str, str]:
    payload: Dict[str, str] = {}
    session_id = _CURRENT_SESSION_ID.get("")
    turn_id = _CURRENT_TURN_ID.get("")
    if session_id:
        payload["session_id"] = session_id
    if turn_id:
        payload["turn_id"] = turn_id
    return payload


# ─── HTTP Tools ───────────────────────────────────────────────────────────────

@tool
async def call_weather_agent(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    date: str = "",
) -> str:
    """
    Get weather conditions for SAR search area coordinates.
    Call for: weather impact, temperature/wind/visibility, exposure risk,
    or historical weather on a specific past date (pass YYYY-MM-DD as date).
    Default coordinates: lat=35.2828, lon=-120.6596.
    """
    payload: Dict[str, Any] = {"lat": lat, "lon": lon, **_correlation_payload()}
    if date:
        payload["date"] = date
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{AGENT_URLS['weather']}/analyze", json=payload)
    return json.dumps(r.json(), default=str)


@tool
async def call_health_agent(
    person_description: str = "",
    current_conditions: str = "",
) -> str:
    """
    Assess health risks for a missing person.
    Call when person age, medical conditions, or survival probability is relevant.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{AGENT_URLS['health']}/analyze", json={
            "person_description": person_description,
            "current_conditions": current_conditions,
            **_correlation_payload(),
        })
    return json.dumps(r.json(), default=str)


@tool
async def call_path_agent(
    start_lat: float = DEFAULT_LAT,
    start_lon: float = DEFAULT_LON,
    age: int = 35,
    cognitive_state: float = 0.9,
    physical_condition: float = 0.8,
    has_vehicle: bool = False,
) -> str:
    """
    Predict missing person movement paths via Monte Carlo terrain simulation.
    Call when location, route, terrain planning, or search area probability is needed.
    Coordinates alone are sufficient — other parameters default automatically.
    Set has_vehicle=true only if the person is known to be on a vehicle or horse.
    """
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{AGENT_URLS['path']}/analyze", json={
            "start_lat": start_lat,
            "start_lon": start_lon,
            "age": age,
            "cognitive_state": cognitive_state,
            "physical_condition": physical_condition,
            "has_vehicle": has_vehicle,
            **_correlation_payload(),
        })
    return json.dumps(r.json(), default=str)


@tool
async def call_history_agent(query: str, context: str = "") -> str:
    """
    Search historical SAR cases for similar situations and successful strategies.
    Call ONLY for: past SAR cases, historical incidents, similar patterns, strategic precedent.
    Do NOT call for weather, health, or real-time data queries.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{AGENT_URLS['history']}/analyze", json={
            "query": query,
            "context": context,
            **_correlation_payload(),
        })
    return json.dumps(r.json(), default=str)


@tool
async def call_interview_agent(
    file_url: str = "",
    transcript_text: str = "",
    witness_name: str = "Unknown",
) -> str:
    """
    Analyze witness interview transcripts or PDF documents.
    Call when: the attached files include a PDF, OR the query contains witness
    testimony, interview transcripts, or any narrative account of seeing the person.
    Pass file_url for PDFs, transcript_text for raw text input.
    """
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(f"{AGENT_URLS['interview']}/analyze", json={
            "file_url": file_url,
            "transcript_text": transcript_text,
            "witness_name": witness_name,
            **_correlation_payload(),
        })
    return json.dumps(r.json(), default=str)


@tool
async def call_photo_agent(image_url: str, description: str = "") -> str:
    """
    Analyze images for persons, objects, and search clues using computer vision.
    Call when attached files include images (jpg/png/gif/webp/bmp).
    image_url must be a presigned MinIO/S3 URL from the attached files list.
    """
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{AGENT_URLS['photo']}/analyze", json={
            "image_url": image_url,
            "description": description,
            **_correlation_payload(),
        })
    return json.dumps(r.json(), default=str)


SAR_TOOLS = [
    call_weather_agent,
    call_health_agent,
    call_path_agent,
    call_history_agent,
    call_interview_agent,
    call_photo_agent,
]

# Maps LangChain tool name → short display name for SSE events
_TOOL_DISPLAY: Dict[str, str] = {
    "call_weather_agent":   "weather",
    "call_health_agent":    "health",
    "call_path_agent":      "path",
    "call_history_agent":   "history",
    "call_interview_agent": "interview",
    "call_photo_agent":     "photo",
}

SAR_SYSTEM_PROMPT = """You are the SAR (Search and Rescue) Command Center AI.

Analyse incoming search-and-rescue queries and coordinate specialist agents to
produce a comprehensive, actionable response.

DISPATCH RULES:
- call_weather_agent: weather, environment, exposure, or a specific past date
- call_health_agent: person age, medical info, or survival probability
- call_path_agent: location, route, terrain, or search area planning; coordinates alone are enough
- call_history_agent: ONLY for past SAR cases or strategic precedent — NOT real-time data
- call_interview_agent: attached PDF files, OR witness testimony/interview text in the query
- call_photo_agent: attached image files (jpg/png/gif/webp/bmp)
- Default coordinates when none given: lat=35.2828, lon=-120.6596
- Call multiple tools in parallel when several domains are relevant

After collecting all results, synthesise them into a clear, prioritised, actionable
SAR briefing. Address the original query directly. Be concise and practical."""


# ─── Agent Setup ──────────────────────────────────────────────────────────────

checkpointer = MemorySaver()
_sar_agent = None


def _get_sar_agent():
    global _sar_agent
    if _sar_agent is None:
        llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME,
            temperature=TEMPERATURE,
            google_api_key=GOOGLE_API_KEY,
        )
        _sar_agent = create_react_agent(
            model=llm,
            tools=SAR_TOOLS,
            checkpointer=checkpointer,
            prompt=SAR_SYSTEM_PROMPT,
        )
    return _sar_agent


# ─── SSE Streaming ────────────────────────────────────────────────────────────

def _clear_session(session_id: str) -> None:
    """Delete a corrupted session checkpoint so the next request starts fresh."""
    try:
        if hasattr(checkpointer, "storage") and session_id in checkpointer.storage:
            del checkpointer.storage[session_id]
            logger.info(f"Cleared corrupted session state: {session_id}")
    except Exception as e:
        logger.warning(f"Could not clear session {session_id}: {e}")


async def run_query_stream(
    query: str,
    session_id: str,
    file_urls: Optional[List[Dict[str, Any]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator yielding SSE-formatted strings.
    Events emitted: agent_start, agent_result, path_data, final, done, error.

    If the session checkpoint contains a dangling tool call (e.g. because a
    previous request crashed mid-flight), the corrupted state is cleared and
    the query is retried automatically once.
    """
    agent = _get_sar_agent()
    config = {"configurable": {"thread_id": session_id}}
    turn_id = str(uuid.uuid4())
    session_token = _CURRENT_SESSION_ID.set(session_id)
    turn_token = _CURRENT_TURN_ID.set(turn_id)

    enhanced = query
    if file_urls:
        enhanced += f"\n\nAttached files: {json.dumps(file_urls)}"

    input_msg = {"messages": [HumanMessage(content=enhanced)]}
    retried = False

    try:
        while True:
            try:
                async for event in agent.astream_events(input_msg, config=config, version="v2"):
                    kind = event["event"]
                    name = event.get("name", "")

                    if kind == "on_tool_start" and name in _TOOL_DISPLAY:
                        display = _TOOL_DISPLAY[name]
                        yield f"event: agent_start\ndata: {display}\n\n"

                    elif kind == "on_tool_end" and name in _TOOL_DISPLAY:
                        display = _TOOL_DISPLAY[name]
                        # Extract path_data from path agent result for map rendering
                        if name == "call_path_agent":
                            try:
                                raw = event["data"].get("output", "")
                                # Newer LangGraph may wrap tool output in a ToolMessage object
                                if hasattr(raw, "content"):
                                    raw = raw.content
                                if isinstance(raw, list):
                                    raw = "".join(
                                        p.get("text", "") if isinstance(p, dict) else str(p)
                                        for p in raw
                                    )
                                result = json.loads(raw) if isinstance(raw, str) else raw
                                inner = result.get("result", result)
                                if "probability_points" in inner:
                                    path_payload = {
                                        "lkp": inner.get("lkp"),
                                        "probability_points": inner["probability_points"],
                                        "person_class": inner.get("person_class"),
                                        "person_profile": inner.get("person_profile"),
                                        "search_radius_km": inner.get("search_radius_km"),
                                    }
                                    yield f"event: path_data\ndata: {json.dumps(path_payload)}\n\n"
                            except Exception as e:
                                logger.warning(f"path_data extraction failed: {e}")
                        yield f"event: agent_result\ndata: **{display}** analysis complete\n\n"

                    elif kind == "on_chat_model_end":
                        # Final synthesis: LLM response with no tool_calls
                        output = event["data"].get("output")
                        if output and hasattr(output, "content") and output.content:
                            if not getattr(output, "tool_calls", None):
                                content = output.content
                                if isinstance(content, list):
                                    content = "".join(
                                        p.get("text", "") if isinstance(p, dict) else str(p)
                                        for p in content
                                    )
                                safe = content.replace("\n", "\ndata: ")
                                yield f"event: final\ndata: {safe}\n\n"
                                yield f"event: done\ndata: {session_id}\n\n"
                break  # stream completed successfully

            except ValueError as e:
                # Dangling tool call in session history — clear and retry once
                if not retried and "ToolMessage" in str(e):
                    logger.warning(
                        f"Corrupted session {session_id} (dangling tool call), "
                        "clearing checkpoint and retrying."
                    )
                    _clear_session(session_id)
                    retried = True
                    continue
                logger.error(f"Stream error for session {session_id}: {e}", exc_info=True)
                yield f"event: error\ndata: {str(e)}\n\n"
                break

            except Exception as e:
                logger.error(f"Stream error for session {session_id}: {e}", exc_info=True)
                yield f"event: error\ndata: {str(e)}\n\n"
                break
    finally:
        _CURRENT_SESSION_ID.reset(session_token)
        _CURRENT_TURN_ID.reset(turn_token)


# ─── Synchronous entry point (CLI / testing) ──────────────────────────────────

def run_query(
    query: str,
    session_id: Optional[str] = None,
    file_urls: Optional[List[Dict[str, Any]]] = None,
    verbose: bool = False,
) -> str:
    import asyncio

    if session_id is None:
        session_id = str(uuid.uuid4())
        logger.info(f"New session: {session_id}")
    else:
        logger.info(f"Continuing session: {session_id}")

    agent = _get_sar_agent()
    config = {"configurable": {"thread_id": session_id}}
    turn_id = str(uuid.uuid4())

    enhanced = query
    if file_urls:
        enhanced += f"\n\nAttached files: {json.dumps(file_urls)}"

    session_token = _CURRENT_SESSION_ID.set(session_id)
    turn_token = _CURRENT_TURN_ID.set(turn_id)
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            agent.ainvoke(
                {"messages": [HumanMessage(content=enhanced)]},
                config=config,
            )
        )
        loop.close()
    finally:
        _CURRENT_SESSION_ID.reset(session_token)
        _CURRENT_TURN_ID.reset(turn_token)
    return result["messages"][-1].content


def get_session_history(session_id: str) -> list:
    config = {"configurable": {"thread_id": session_id}}
    try:
        state = _get_sar_agent().get_state(config)
        if state and state.values:
            return [
                {
                    "role": "user" if isinstance(m, HumanMessage) else "assistant",
                    "content": m.content,
                }
                for m in state.values.get("messages", [])
            ]
    except Exception as e:
        logger.warning(f"Could not retrieve session history: {e}")
    return []
