# agents/weather/main.py

"""
Weather Agent (v1.1)

This agent now uses the standardized A2A message envelope and the shared RedisBus 
from `shared/` for all inter-agent communication.
"""

import os
import time
import logging
import requests

from shared import wrap_envelope, RedisBus

AGENT_NAME = os.getenv("AGENT_NAME", "weather-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1.1")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_NAME = "weather.forecast.raw"
DEAD_LETTER_STREAM = "system.dead_letter"
LATITUDE = os.getenv("LATITUDE", "35.2828")
LONGITUDE = os.getenv("LONGITUDE", "-120.6596")
API_USER_AGENT = "SAR-Multi-Agent-System"
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


def fetch_and_publish_weather(bus: RedisBus):
    """
    Fetches weather data, wraps it in the standard envelope,
    and publishes it using the provided RedisBus instance.
    """
    headers = {"User-Agent": API_USER_AGENT}
    points_url = f"https://api.weather.gov/points/{LATITUDE},{LONGITUDE}"

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

        payload = {
            "source_api": "NOAA NWS API",
            "location": {
                "latitude": float(LATITUDE),
                "longitude": float(LONGITUDE),
            },
            "forecasts": forecast_periods
        }
        
        message_to_publish = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=STREAM_NAME
        )
        bus.publish(message_to_publish)

    except Exception as e:
        logger.error(f"An unhandled error occurred: {e}", exc_info=True)
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": f"Failed while fetching weather for LAT={LATITUDE}, LON={LONGITUDE}"
        }
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME, 
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM
        )
        bus.publish(error_message)


def main():
    logger.info(f"Initializing {AGENT_NAME}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logger.info(f"{AGENT_NAME} starting up. Update interval: {UPDATE_INTERVAL_SECONDS} seconds.")
    while True:
        logger.info("Starting new weather fetch cycle.")
        fetch_and_publish_weather(bus)
        logger.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()