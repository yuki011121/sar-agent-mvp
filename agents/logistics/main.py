# agents/logistics/main.py

import os
import time
import logging
import json
import requests
import redis
from datetime import datetime
import random

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_VERSION = "logistics-chief-v1.0"
STREAM_NAME = "logistics.requests.raw"
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600))  # 1 hour 

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

RESOURCE_TYPES = ["Medical Kit", "Food Ration", "Water", "Fuel", "Tent", "Radio"]

def simulate_resource_request():
    """Simulates a resource request generated during a SAR mission."""

    request = {
        "timestamp_utc": datetime.now().isoformat() + "Z",
        "agent_name": AGENT_VERSION,
        "incident_id": f"INC-{random.randint(1000, 9999)}",
        "requested_item": random.choice(RESOURCE_TYPES),
        "quantity": random.randint(1, 20),
        "priority": random.choice(["Low", "Medium", "High"]),
        "location": {
            "lat": round(random.uniform(35.0, 36.0), 4),
            "lon": round(random.uniform(-121.0, -120.0), 4)
        }
    }

    logging.info(f"Resource Request = {request}")

    return request

def publish_to_redis(message: dict):
    """Publishes the given message to the configured Redis Stream."""
    try:
        message_id = redis_client.xadd(STREAM_NAME, {"data": json.dumps(message)})
        logging.info(f"Successfully published message to stream '{STREAM_NAME}' with ID {message_id}")
    except redis.exceptions.RedisError as e:
        logging.error(f"Failed to publish to Redis: {e}")


def main():
    """Main loop for the Logistics Chief."""
    logging.info(f"{AGENT_VERSION} starting up. Update interval: {UPDATE_INTERVAL_SECONDS} seconds.")

    while True:
        request_data = simulate_resource_request()

        if request_data:
            publish_to_redis(request_data)
        else:
            logging.warning("No resource request was made in this cycle.")
            
        logging.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()