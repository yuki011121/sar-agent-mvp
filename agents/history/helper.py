import os
import time
import logging
import redis
from dotenv import load_dotenv
from typing import List, Generator

from shared.a2a_envelope import wrap_envelope
from shared.a2a_envelope import StandardMessage, parse_message_from_stream
from shared.redis_bus import RedisBus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = "history-agent"
STREAM_NAME_OUT = "history.in.raw"
AGENT_VERSION = "1.1"

def main():
    try:
        logging.info("Printing to in stream")
        print(REDIS_URL)
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logging.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return
    payload = {
         'outcome': 'search',
         'terrain': 'mountainous',
         'category': 'hiker',
         'filter': {
             'type': 'location',
             'filter_value': "us-ky"
         },
         'additional': "This person might have dementia and is likes to go to common spaces when wandering"
    }
    message_to_publish = wrap_envelope(
        payload=payload,
        source_name=AGENT_NAME,
        source_version=AGENT_VERSION,
        target_stream=STREAM_NAME_OUT
    )
    bus.publish(message_to_publish)


if __name__ == "__main__":
    main()