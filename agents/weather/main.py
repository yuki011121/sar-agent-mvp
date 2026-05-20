# agents/weather/main.py

"""
Weather Agent (v1.2)

This agent uses the standardized A2A message envelope and the shared RedisBus 
from `shared/` for all inter-agent communication.

Features:
- Periodic weather publishing (every UPDATE_INTERVAL_SECONDS)
- On-demand weather queries via weather.query.raw stream
- Task ID correlation for dispatch/response pattern
"""

import os
import time
import logging
import threading
import requests
from datetime import date as date_type
from typing import Optional, Dict, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from shared import wrap_envelope, RedisBus, parse_message_from_stream

AGENT_NAME = os.getenv("AGENT_NAME", "weather-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1.2")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_NAME = "weather.forecast.raw"
QUERY_INPUT_STREAM = "weather.query.raw"
DEAD_LETTER_STREAM = "system.dead_letter"
DEFAULT_LATITUDE = float(os.getenv("LATITUDE", "35.2828"))
DEFAULT_LONGITUDE = float(os.getenv("LONGITUDE", "-120.6596"))
API_USER_AGENT = "SAR-Multi-Agent-System"
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600))
HTTP_PORT = int(os.getenv("HTTP_PORT", "8001"))

# Module-level bus for use in HTTP endpoints
_bus: Optional[RedisBus] = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)

WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def fetch_historical_weather(lat: float, lon: float, query_date: str) -> Optional[Dict[str, Any]]:
    """Fetch historical weather for a specific past date using Open-Meteo archive API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": query_date,
        "end_date": query_date,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode,windspeed_10m_max,precipitation_sum",
        "hourly": "temperature_2m,windspeed_10m,weathercode,precipitation,visibility",
        "timezone": "auto",
    }
    try:
        logger.info(f"Fetching historical weather for ({lat}, {lon}) on {query_date}")
        resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        hourly = data.get("hourly", {})

        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        winds = hourly.get("windspeed_10m", [])
        codes = hourly.get("weathercode", [])
        precip = hourly.get("precipitation", [])
        vis = hourly.get("visibility", [])

        period_labels = ["Night (0-6h)", "Morning (6-12h)", "Afternoon (12-18h)", "Evening (18-24h)"]
        hourly_breakdown = []
        for block_idx in range(4):
            i = block_idx * 6
            block_temps = [t for t in temps[i:i+6] if t is not None]
            block_winds = [w for w in winds[i:i+6] if w is not None]
            block_precip = [p for p in precip[i:i+6] if p is not None]
            block_vis = [v for v in vis[i:i+6] if v is not None]
            block_code = codes[i] if i < len(codes) and codes[i] is not None else None
            hourly_breakdown.append({
                "period": period_labels[block_idx],
                "avg_temp_c": round(sum(block_temps) / len(block_temps), 1) if block_temps else None,
                "max_wind_kmh": round(max(block_winds), 1) if block_winds else None,
                "total_precip_mm": round(sum(block_precip), 1) if block_precip else None,
                "avg_visibility_m": int(sum(block_vis) / len(block_vis)) if block_vis else None,
                "conditions": WMO_CODES.get(block_code, f"Code {block_code}") if block_code is not None else "Unknown",
            })

        daily_code = daily.get("weathercode", [None])[0]
        return {
            "source_api": "Open-Meteo Historical Archive",
            "query_date": query_date,
            "location": {"latitude": lat, "longitude": lon},
            "daily_summary": {
                "max_temp_c": daily.get("temperature_2m_max", [None])[0],
                "min_temp_c": daily.get("temperature_2m_min", [None])[0],
                "max_wind_kmh": daily.get("windspeed_10m_max", [None])[0],
                "total_precip_mm": daily.get("precipitation_sum", [None])[0],
                "conditions": WMO_CODES.get(daily_code, f"Code {daily_code}") if daily_code is not None else "Unknown",
            },
            "hourly_breakdown": hourly_breakdown,
        }
    except Exception as e:
        logger.error(f"Error fetching historical weather for ({lat}, {lon}) on {query_date}: {e}")
        return None


def fetch_weather_data(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Fetches weather data for given coordinates.
    Returns the payload dict or None on error.
    """
    headers = {"User-Agent": API_USER_AGENT}
    points_url = f"https://api.weather.gov/points/{lat},{lon}"

    try:
        logger.info(f"Fetching metadata from {points_url}")
        points_response = requests.get(points_url, headers=headers, timeout=HTTP_TIMEOUT)
        points_response.raise_for_status()
        points_data = points_response.json()["properties"]
        forecast_url = points_data["forecast"]

        logger.info(f"Fetching actual forecast data from {forecast_url}")
        forecast_response = requests.get(forecast_url, headers=headers, timeout=HTTP_TIMEOUT)
        forecast_response.raise_for_status()
        forecast_periods = forecast_response.json()["properties"]["periods"]

        return {
            "source_api": "NOAA NWS API",
            "location": {
                "latitude": lat,
                "longitude": lon,
            },
            "forecasts": forecast_periods
        }
    except Exception as e:
        logger.error(f"Error fetching weather for ({lat}, {lon}): {e}")
        return None


def fetch_and_publish_weather(bus: RedisBus, task_id: Optional[str] = None,
                               lat: Optional[float] = None, lon: Optional[float] = None,
                               query_date: Optional[str] = None,
                               session_id: Optional[str] = None,
                               turn_id: Optional[str] = None):
    """
    Fetches weather data, wraps it in the standard envelope,
    and publishes it using the provided RedisBus instance.
    If query_date (YYYY-MM-DD) is provided and is in the past, fetches historical data.
    """
    use_lat = lat if lat is not None else DEFAULT_LATITUDE
    use_lon = lon if lon is not None else DEFAULT_LONGITUDE

    try:
        if query_date:
            payload = fetch_historical_weather(use_lat, use_lon, query_date)
        else:
            payload = fetch_weather_data(use_lat, use_lon)
        
        if payload:
            # Include task_id for correlation if provided
            if task_id:
                payload["task_id"] = task_id
            if session_id:
                payload["session_id"] = session_id
            if turn_id:
                payload["turn_id"] = turn_id

            message_to_publish = wrap_envelope(
                payload=payload,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=STREAM_NAME
            )
            bus.publish(message_to_publish)
            logger.info(f"Published weather data to {STREAM_NAME}" +
                       (f" (task_id: {task_id})" if task_id else ""))
            return payload
        else:
            raise Exception(f"Failed to fetch weather data for ({use_lat}, {use_lon})")

    except Exception as e:
        logger.error(f"An unhandled error occurred: {e}", exc_info=True)
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": f"Failed while fetching weather for LAT={use_lat}, LON={use_lon}"
        }
        if task_id:
            error_payload["task_id"] = task_id
        if session_id:
            error_payload["session_id"] = session_id
        if turn_id:
            error_payload["turn_id"] = turn_id
            
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME, 
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM
        )
        bus.publish(error_message)


def periodic_publisher(bus: RedisBus):
    """Background thread for periodic weather publishing."""
    logger.info(f"Periodic publisher started. Interval: {UPDATE_INTERVAL_SECONDS}s")
    while True:
        logger.info("Starting periodic weather fetch cycle.")
        fetch_and_publish_weather(bus)
        logger.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


def query_listener(bus: RedisBus):
    """Listen for on-demand weather queries via weather.query.raw stream."""
    logger.info(f"Query listener started. Listening on: {QUERY_INPUT_STREAM}")
    
    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-query-group",
            consumer_name=f"{AGENT_NAME}-query-consumer",
            streams=[QUERY_INPUT_STREAM],
            block_ms=5000
        ):
            try:
                payload = message.payload
                logger.info(f"Received weather query: {payload}")
                
                # Extract parameters
                task_id = payload.get("task_id")
                session_id = payload.get("session_id")
                turn_id = payload.get("turn_id")
                lat = payload.get("lat") or payload.get("latitude")
                lon = payload.get("lon") or payload.get("longitude")
                query_date = payload.get("date") or payload.get("query_date")

                if lat is not None:
                    lat = float(lat)
                if lon is not None:
                    lon = float(lon)

                fetch_and_publish_weather(
                    bus,
                    task_id=task_id,
                    lat=lat,
                    lon=lon,
                    query_date=query_date,
                    session_id=session_id,
                    turn_id=turn_id,
                )
                
            except Exception as e:
                logger.error(f"Error processing query message: {e}")
                
    except Exception as e:
        logger.error(f"Query listener error: {e}")


# ============================================================================
# HTTP Server (A2A-compatible)
# ============================================================================

class WeatherRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    date: Optional[str] = None  # YYYY-MM-DD for historical
    session_id: Optional[str] = None
    turn_id: Optional[str] = None


_http_app = FastAPI(title="weather-agent")


@_http_app.get("/.well-known/agent.json")
def agent_card():
    return JSONResponse({
        "name": AGENT_NAME,
        "description": "Provides current and historical weather data for SAR search coordinates.",
        "version": AGENT_VERSION,
        "url": f"http://{AGENT_NAME}:{HTTP_PORT}",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": [{"id": "analyze", "name": "Weather Analysis",
                    "description": "Fetch current or historical weather for a lat/lon location.",
                    "inputModes": ["application/json"],
                    "outputModes": ["application/json"]}],
    })


@_http_app.post("/analyze")
def analyze(req: WeatherRequest):
    if _bus is None:
        return JSONResponse({"error": "Redis not ready"}, status_code=503)
    try:
        payload = fetch_and_publish_weather(
            _bus,
            lat=req.lat,
            lon=req.lon,
            query_date=req.date,
            session_id=req.session_id,
            turn_id=req.turn_id,
        )
        return {"agent": AGENT_NAME, "status": "success", "result": payload}
    except Exception as e:
        logger.error(f"HTTP /analyze error: {e}")
        return JSONResponse({"agent": AGENT_NAME, "error": str(e)}, status_code=500)


def _start_http_server():
    uvicorn.run(_http_app, host="0.0.0.0", port=HTTP_PORT, log_level="warning")


def main():
    global _bus
    logger.info(f"Initializing {AGENT_NAME} v{AGENT_VERSION}...")

    try:
        _bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return

    logger.info(f"{AGENT_NAME} starting up.")

    # Start HTTP server in background thread
    http_thread = threading.Thread(target=_start_http_server, daemon=True)
    http_thread.start()
    logger.info(f"HTTP server started on port {HTTP_PORT}")

    # Start periodic publisher in background thread
    periodic_thread = threading.Thread(target=periodic_publisher, args=(_bus,), daemon=True)
    periodic_thread.start()

    # Run query listener in main thread
    query_listener(_bus)


if __name__ == "__main__":
    main()
