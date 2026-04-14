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
from typing import Optional, Dict, Any

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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


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
                               lat: Optional[float] = None, lon: Optional[float] = None):
    """
    Fetches weather data, wraps it in the standard envelope,
    and publishes it using the provided RedisBus instance.
    """
    use_lat = lat if lat is not None else DEFAULT_LATITUDE
    use_lon = lon if lon is not None else DEFAULT_LONGITUDE

    try:
        payload = fetch_weather_data(use_lat, use_lon)
        
        if payload:
            # Include task_id for correlation if provided
            if task_id:
                payload["task_id"] = task_id
            
            message_to_publish = wrap_envelope(
                payload=payload,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=STREAM_NAME
            )
            bus.publish(message_to_publish)
            logger.info(f"Published weather data to {STREAM_NAME}" + 
                       (f" (task_id: {task_id})" if task_id else ""))
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
                lat = payload.get("lat") or payload.get("latitude")
                lon = payload.get("lon") or payload.get("longitude")
                
                # Use defaults if not provided
                if lat is not None:
                    lat = float(lat)
                if lon is not None:
                    lon = float(lon)
                
                # Process the query
                fetch_and_publish_weather(bus, task_id=task_id, lat=lat, lon=lon)
                
            except Exception as e:
                logger.error(f"Error processing query message: {e}")
                
    except Exception as e:
        logger.error(f"Query listener error: {e}")


def main():
    logger.info(f"Initializing {AGENT_NAME} v{AGENT_VERSION}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logger.info(f"{AGENT_NAME} starting up.")
    
    # Start periodic publisher in background thread
    periodic_thread = threading.Thread(target=periodic_publisher, args=(bus,), daemon=True)
    periodic_thread.start()
    
    # Run query listener in main thread
    query_listener(bus)


if __name__ == "__main__":
    main()