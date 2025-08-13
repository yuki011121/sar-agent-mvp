# shared/redis_bus.py
"""
By using the `RedisBus`, agents can communicate reliably without needing to
manage their own connections or message formats. It is tightly integrated with
the `StandardMessage` format from `a2a_envelope.py`.

Usage
-----
A message publisher:
>>> from shared.a2a_envelope import wrap_envelope
>>> from shared.redis_bus import RedisBus
>>> bus = RedisBus()
>>> msg = wrap_envelope(payload={"data": 123}, ...)
>>> bus.publish(msg)

A message subscriber:
>>> bus = RedisBus()
>>> streams = ['clues.photo.raw', 'clues.interview.raw']
>>> for message in bus.subscribe("intelligence-consumers", "clue-meister-1", streams):
...     print(f"Received message from {message.envelope.source_agent.name}")
...     # Your processing logic here
"""

import os
import time
import logging
import redis
from typing import List, Generator

from .a2a_envelope import StandardMessage, parse_message_from_stream

logger = logging.getLogger(__name__)

class RedisBus:
    def __init__(self, redis_url: str | None = None):
        """
        Args:
            redis_url (str, optional): Redis URL. If None, falls back to
                                       the REDIS_URL environment variable.
        """
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        try:
            self.client = redis.Redis.from_url(url, decode_responses=False)
            self.client.ping()
            logger.info(f"RedisBus successfully connected -> {url}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"RedisBus could not connect to Redis: {e}", exc_info=True)
            raise

    def publish(self, message: StandardMessage):
        target_stream = message.envelope.target_stream
        try:
            message_body = message.model_dump_json().encode('utf-8')
            self.client.xadd(target_stream, {"body": message_body})
            logger.debug(f"Published message {message.envelope.message_id} -> {target_stream}")
        except redis.RedisError as e:
            logger.error(f"Failed to publish to stream '{target_stream}': {e}", exc_info=True)

    def _ensure_group(self, stream_name: str, group_name: str):
        """Internal helper to create a stream and consumer group if they don't exist."""
        try:
            self.client.xgroup_create(stream_name, group_name, id='0', mkstream=True)
            logger.info(f"Created consumer group '{group_name}' on stream '{stream_name}'.")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in e.args[0]:
                logger.debug(f"Group '{group_name}' on stream '{stream_name}' already exists.")
            else:
                raise

    def subscribe(
        self, group_name: str, consumer_name: str, streams: List[str], block_ms: int = 0
    ) -> Generator[StandardMessage, None, None]:
        """Subscribes to streams and yields parsed messages."""
        stream_mapping = {s: '>' for s in streams}
        for stream in streams:
            self._ensure_group(stream, group_name)
        
        logger.info(f"Consumer '{consumer_name}' listening on streams: {streams}")
        
        while True:
            try:
                response = self.client.xreadgroup(group_name, consumer_name, stream_mapping, count=1, block=block_ms)
                if not response:
                    continue

                stream_b, messages = response[0]
                msg_id, data_b = messages[0]
                
                decoded_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in data_b.items()}
                parsed_message = parse_message_from_stream(decoded_data)

                self.client.xack(stream_b, group_name, msg_id)

                if parsed_message:
                    yield parsed_message
                else:
                    logger.warning("Unable to parse message %s on %s. Message acknowledged and skipped.", 
                                   msg_id.decode(), stream_b.decode())

            except Exception as e:
                logger.error(f"Unexpected error in subscribe loop: {e}", exc_info=True)
                time.sleep(1)