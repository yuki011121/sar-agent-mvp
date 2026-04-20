#!/usr/bin/env python3
"""
LangChain Tools for SAR Command Agent

These tools read data from Redis streams and provide it to the LangGraph nodes.
Each tool corresponds to one specialist domain.
"""

import os
import json
import logging
from typing import Optional

import redis
from langchain_core.tools import tool

from shared import parse_message_from_stream

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Logger
logger = logging.getLogger("command-agent-tools")

# Redis client (lazy initialized)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Redis client connected")
    return _redis_client


def read_stream_data(stream_name: str, count: int = 5) -> str:
    """
    Read latest messages from a Redis stream.
    
    Returns formatted string with the data for LLM consumption.
    """
    client = get_redis_client()
    
    try:
        messages = client.xrevrange(stream_name, count=count)
        if not messages:
            return f"No data available in {stream_name}"
        
        results = []
        for msg_id, data in messages:
            try:
                parsed = parse_message_from_stream(data)
                if parsed:
                    # Extract payload from StandardMessage
                    if hasattr(parsed, 'payload'):
                        payload = parsed.payload
                    elif isinstance(parsed, dict) and 'payload' in parsed:
                        payload = parsed['payload']
                    else:
                        payload = parsed.model_dump() if hasattr(parsed, 'model_dump') else parsed
                    
                    results.append({
                        "timestamp": msg_id,
                        "data": payload
                    })
            except Exception as e:
                # Fallback: try direct parsing
                try:
                    if 'body' in data:
                        body = json.loads(data['body']) if isinstance(data['body'], str) else data['body']
                        results.append({
                            "timestamp": msg_id,
                            "data": body.get('payload', body)
                        })
                except:
                    logger.warning(f"Could not parse message {msg_id}: {e}")
        
        if not results:
            return f"No parseable data in {stream_name}"
        
        return json.dumps(results, indent=2, ensure_ascii=False, default=str)
    
    except Exception as e:
        logger.error(f"Error reading {stream_name}: {e}")
        return f"Error reading {stream_name}: {str(e)}"


# ============================================================================
# LangChain Tools - One per specialist domain
# ============================================================================

@tool
def get_weather_data() -> str:
    """
    Get current weather forecast data for the search area.
    
    Returns weather conditions including temperature, wind speed, visibility,
    precipitation, and other factors that affect search and rescue operations.
    Use this to assess weather impact on search operations.
    """
    return read_stream_data("weather.forecast.raw")


@tool
def get_health_assessment() -> str:
    """
    Get health risk assessment for the missing person.
    
    Returns health analysis including risk factors based on age, medical conditions,
    time elapsed, weather exposure, and survival probability estimates.
    Use this to understand medical urgency and prioritize search efforts.
    """
    return read_stream_data("health.assessment.raw")


@tool
def get_history_cases() -> str:
    """
    Get similar historical SAR cases from the database.
    
    Returns relevant past cases with similar characteristics (terrain, subject profile,
    conditions) and their outcomes, search strategies that worked, and lessons learned.
    Use this to inform search strategy based on historical patterns.
    """
    return read_stream_data("history.out.raw")


@tool
def get_photo_analysis() -> str:
    """
    Get photo analysis results from image processing.
    
    Returns object detection results from search area photos including identified
    persons, vehicles, equipment, and other relevant objects with their locations.
    Use this to identify potential clues or sightings from visual data.
    """
    return read_stream_data("photo.analysis.raw")


@tool
def get_path_analysis() -> str:
    """
    Get terrain and path analysis for the search area.
    
    Returns terrain difficulty assessment, recommended search routes, accessibility
    analysis, elevation data, and identified hazards in the search area.
    Use this to plan search patterns and allocate resources by terrain.
    """
    return read_stream_data("path.analysis.raw")


@tool
def get_logistics_status() -> str:
    """
    Get current logistics and resource status.
    
    Returns information about available resources, equipment requests, personnel
    deployment, and supply status for the search operation.
    Use this to understand resource constraints and deployment options.
    """
    return read_stream_data("logistics.requests.raw")


@tool
def get_interview_analysis() -> str:
    """
    Get analysis of witness interviews and statements.
    
    Returns extracted information from witness interviews including last seen
    locations, behavioral patterns, and other relevant observations.
    Use this to gather human intelligence about the missing person.
    """
    return read_stream_data("interview.analysis.raw")


@tool
def get_cluemeister_analysis() -> str:
    """
    Get comprehensive analysis from the ClueMeister aggregation agent.
    
    Returns synthesized information from all agents, discovered correlations,
    knowledge graph insights, and coordinated analysis across all data sources.
    Use this for a holistic view of all available intelligence.
    """
    return read_stream_data("cluemeister.analysis.raw")


# ============================================================================
# Task Dispatch Tools - Active task assignment to agents
# ============================================================================

@tool
def dispatch_history_query(query: str, context: str = "") -> str:
    """
    Dispatch a query to the History Agent for similar case lookup.
    
    Use this when you need to find historical SAR cases similar to the current situation.
    The History Agent will search the ISRID database and return relevant cases.
    
    Args:
        query: The search query (e.g., "elderly missing in forest with dementia")
        context: Additional context about the current case
        
    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams
    
    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("history")
    
    payload = {
        "query": query,
        "context": context,
        "mission_context": context,
    }
    
    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to History Agent: {task_id}"


@tool
def dispatch_interview_analysis(
    file_url: str = "",
    transcript_text: str = "",
    witness_name: str = "Unknown",
) -> str:
    """
    Dispatch interview transcript or PDF document for analysis by the Interview Agent.

    Use file_url for PDF documents uploaded to MinIO (preferred).
    Use transcript_text for raw text transcripts.

    Args:
        file_url: MinIO/S3 presigned URL of a PDF document
        transcript_text: Raw transcript text (for direct text input)
        witness_name: Name of witness or document identifier

    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams

    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("interview")

    payload = {
        "file_url": file_url,
        "transcript_text": transcript_text,
        "witness_name": witness_name,
        "source": "command-agent-dispatch",
    }

    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to Interview Agent: {task_id}"


@tool
def dispatch_photo_analysis(image_url: str, description: str = "") -> str:
    """
    Dispatch an image for analysis by the Photo Analysis Agent.
    
    Use this when you have an image URL (from MinIO/S3) that needs to be
    analyzed for objects, persons, and potential search clues.
    
    Args:
        image_url: URL of the image to analyze (presigned MinIO/S3 URL)
        description: Optional description of what to look for
        
    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams
    
    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("photo")
    
    payload = {
        "image_url": image_url,
        "description": description,
        "analysis_type": "full",  # full, persons_only, objects_only
    }
    
    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to Photo Analysis Agent: {task_id}"


@tool
def dispatch_weather_query(latitude: float, longitude: float) -> str:
    """
    Dispatch a weather query for specific coordinates.
    
    Use this when you need current weather conditions for a specific location
    rather than the default search area.
    
    Args:
        latitude: Latitude of the location
        longitude: Longitude of the location
        
    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams
    
    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("weather")
    
    payload = {
        "latitude": latitude,
        "longitude": longitude,
        "request_type": "on_demand",
    }
    
    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to Weather Agent: {task_id}"


@tool
def dispatch_health_assessment(person_info: str, conditions: str = "") -> str:
    """
    Dispatch a health risk assessment request.
    
    Use this when you need an updated health assessment for a missing person
    based on new information or changed conditions.
    
    Args:
        person_info: Description of the person (age, conditions, medications)
        conditions: Current environmental/situational conditions
        
    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams
    
    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("health")
    
    payload = {
        "person_description": person_info,
        "current_conditions": conditions,
        "assessment_type": "on_demand",
    }
    
    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to Health Agent: {task_id}"


@tool  
def dispatch_path_analysis(start_lat: float, start_lon: float, end_lat: float = None, end_lon: float = None) -> str:
    """
    Dispatch a path/terrain analysis request.
    
    Use this when you need terrain analysis or route planning for the search area.
    
    Args:
        start_lat: Starting latitude
        start_lon: Starting longitude
        end_lat: Optional ending latitude (for route analysis)
        end_lon: Optional ending longitude (for route analysis)
        
    Returns:
        task_id that can be used to track and retrieve results
    """
    from .task_tracker import get_tracker, get_agent_streams
    
    tracker = get_tracker()
    input_stream, output_stream = get_agent_streams("path")
    
    payload = {
        "start": {"lat": start_lat, "lon": start_lon},
        "end": {"lat": end_lat, "lon": end_lon} if end_lat and end_lon else None,
        "analysis_type": "route" if end_lat else "terrain",
    }
    
    task_id = tracker.submit_task(input_stream, output_stream, payload)
    return f"Task dispatched to Path Analysis Agent: {task_id}"


@tool
def wait_for_task_results(task_ids: str, timeout: int = 30) -> str:
    """
    Wait for dispatched tasks to complete and retrieve their results.
    
    Use this after dispatching one or more tasks to collect their results.
    
    Args:
        task_ids: Comma-separated list of task IDs to wait for
        timeout: Maximum seconds to wait (default: 30)
        
    Returns:
        JSON string with results for each task
    """
    from .task_tracker import get_tracker
    import json
    
    tracker = get_tracker()
    ids = [tid.strip() for tid in task_ids.split(",")]
    
    results = tracker.wait_for_tasks(ids, timeout=timeout)
    
    # Format results for LLM consumption
    formatted = []
    for task_id, result in results.items():
        if "error" in result:
            formatted.append(f"Task {task_id}: ERROR - {result.get('message', result['error'])}")
        else:
            formatted.append(f"Task {task_id}: {json.dumps(result, indent=2, default=str)}")
    
    return "\n\n".join(formatted)


# ============================================================================
# Tool Registry
# ============================================================================

# Read-only tools (passive data access)
READ_TOOLS = [
    get_weather_data,
    get_health_assessment,
    get_history_cases,
    get_photo_analysis,
    get_path_analysis,
    get_logistics_status,
    get_interview_analysis,
    get_cluemeister_analysis,
]

# Dispatch tools (active task assignment)
DISPATCH_TOOLS = [
    dispatch_history_query,
    dispatch_interview_analysis,
    dispatch_photo_analysis,
    dispatch_weather_query,
    dispatch_health_assessment,
    dispatch_path_analysis,
    wait_for_task_results,
]

# All available tools for the command agent
ALL_TOOLS = READ_TOOLS + DISPATCH_TOOLS

# Tool name to function mapping
TOOL_MAP = {tool.name: tool for tool in ALL_TOOLS}


def get_tools_for_specialist(specialist: str) -> list:
    """Get the primary tool for a specialist domain."""
    specialist_tools = {
        "weather": [get_weather_data, dispatch_weather_query],
        "health": [get_health_assessment, dispatch_health_assessment],
        "history": [get_history_cases, dispatch_history_query],
        "photo": [get_photo_analysis, dispatch_photo_analysis],
        "path": [get_path_analysis, dispatch_path_analysis],
        "logistics": [get_logistics_status],
        "interview": [get_interview_analysis, dispatch_interview_analysis],
    }
    return specialist_tools.get(specialist, ALL_TOOLS)
