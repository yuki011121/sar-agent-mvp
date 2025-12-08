"""
Redis client module for the photo analysis agent.
Handles Redis connection and message publishing.
"""

import os
import time
import json
import logging
import redis
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class RedisClient:
    """Handles Redis operations for the photo analysis agent."""
    
    def __init__(self, redis_url: str, output_stream: str, max_retries: int = 3, retry_delay: int = 5):
        """Initialize the Redis client."""
        self.redis_url = redis_url
        self.output_stream = output_stream
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client = None
    
    def connect(self) -> bool:
        """Establish Redis connection with retry logic."""
        for attempt in range(self.max_retries):
            try:
                self.client = redis.Redis.from_url(self.redis_url, decode_responses=True)
                self.client.ping()
                logger.info(f"Successfully connected to Redis at {self.redis_url}")
                return True
            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.critical("Failed to connect to Redis after all retries")
                    return False
            except Exception as e:
                logger.error(f"Unexpected Redis error: {e}")
                return False
        
        return False
    
    def publish_message(self, message: Dict[str, Any]) -> bool:
        """Safely publish message to Redis with retry logic."""
        if self.client is None:
            logger.error("Redis client not connected")
            return False
        
        for attempt in range(self.max_retries):
            try:
                message_id = self.client.xadd(self.output_stream, {"data": json.dumps(message)})
                logger.info(f"Published analysis to stream '{self.output_stream}' with ID {message_id}")
                return True
            except redis.exceptions.RedisError as e:
                logger.error(f"Redis publish attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"Retrying Redis publish in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Failed to publish to Redis after all retries")
                    return False
            except Exception as e:
                logger.error(f"Unexpected Redis error: {e}")
                return False
        
        return False
    
    def is_connected(self) -> bool:
        """Check if Redis client is connected."""
        if self.client is None:
            return False
        
        try:
            self.client.ping()
            return True
        except Exception:
            return False
    
    def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            try:
                self.client.close()
                logger.info("Disconnected from Redis")
            except Exception as e:
                logger.warning(f"Error disconnecting from Redis: {e}")
            finally:
                self.client = None
