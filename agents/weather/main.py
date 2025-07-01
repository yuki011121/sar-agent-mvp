# agents/weather/main.py

import os
import time
import logging
import json
import requests
import redis
from datetime import datetime

LATITUDE = os.getenv("LATITUDE", "35.2828")
LONGITUDE = os.getenv("LONGITUDE", "-120.6596")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600)) # 每小时更新一次
AGENT_VERSION = "weather-agent-v1.0"
STREAM_NAME = "weather.forecast.raw"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)


def fetch_and_process_weather():
    """Fetches weather data from the NOAA API and transforms it into our standard format."""
    headers = {"User-Agent": "SAR-Agent-PoC (github.com/yuki011121/sar-agent-mvp)"}
    
    points_url = f"https://api.weather.gov/points/{LATITUDE},{LONGITUDE}"
    try:
        logging.info(f"Fetching metadata from {points_url}")
        points_response = requests.get(points_url, headers=headers, timeout=15)
        points_response.raise_for_status()
        points_data = points_response.json()["properties"]
        forecast_url = points_data["forecast"]
        logging.info(f"Successfully retrieved forecast URL: {forecast_url}")

        logging.info("Fetching actual forecast data...")
        forecast_response = requests.get(forecast_url, headers=headers, timeout=15)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()["properties"]

        standardized_forecasts = []
        for period in forecast_data.get("periods", []):
            standardized_forecasts.append({
                "period_name": period.get("name"),
                "start_time": period.get("startTime"),
                "end_time": period.get("endTime"),
                "is_daytime": period.get("isDaytime"),
                "temperature": period.get("temperature"),
                "temperature_unit": period.get("temperatureUnit"),
                "wind_speed": period.get("windSpeed"),
                "wind_direction": period.get("windDirection"),
                "precipitation_probability": period.get("probabilityOfPrecipitation", {}).get("value", 0) or 0,
                "short_forecast": period.get("shortForecast"),
                "detailed_forecast": period.get("detailedForecast")
            })
        
        output_message = {
            "metadata": {
                "agent_name": AGENT_VERSION,
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "source": "NOAA NWS API"
            },
            "location": {
                "latitude": float(LATITUDE),
                "longitude": float(LONGITUDE),
                "grid_id": points_data.get("gridId"),
                "grid_x": points_data.get("gridX"),
                "grid_y": points_data.get("gridY")
            },
            "forecasts": standardized_forecasts
        }
        return output_message

    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP request failed: {e}")
    except (KeyError, json.JSONDecodeError) as e:
        logging.error(f"Failed to parse API response: {e}")
    
    return None

def publish_to_redis(message: dict):
    """Publishes the given message to the configured Redis Stream."""
    try:
        message_id = redis_client.xadd(STREAM_NAME, {"data": json.dumps(message)})
        logging.info(f"Successfully published message to stream '{STREAM_NAME}' with ID {message_id}")
    except redis.exceptions.RedisError as e:
        logging.error(f"Failed to publish to Redis: {e}")

def main():
    """Main loop for the Weather Agent."""
    logging.info(f"{AGENT_VERSION} starting up. Update interval: {UPDATE_INTERVAL_SECONDS} seconds.")
    while True:
        logging.info("Starting new weather fetch cycle.")
        weather_data = fetch_and_process_weather()
        
        if weather_data:
            publish_to_redis(weather_data)
        else:
            logging.warning("No weather data was fetched in this cycle.")
            
        logging.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()