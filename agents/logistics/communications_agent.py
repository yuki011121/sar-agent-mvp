# agents/logistics/communications_agent.py

import json
from datetime import datetime
from typing import Dict, Any
from agents.base_agent import SARBaseAgent
from google import genai
import os
import redis
import threading
import time
import logging


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Redis connection (used for both Pub/Sub and the Blackboard Stream)
# TODO: implement redis_bus.py under the utils folder
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)

class CommunicationsAgent(SARBaseAgent):
    def __init__(self, name="communications", knowledge_base=None):
        # TODO: better system message/job description prompt needed 
        system_message = """
                         You are the Communications Agent in a FEMA-aligned SAR operation.

                         You are responsible for ensuring all units are connected via radio, satellite, and repeaters.

                         Monitor signal quality and report any anomalies immediately.
                         
                         Respond with authoritative, concise, and mission-critical guidance.
                         """
        
        super().__init__(
            name = name,
            role = "Communications Agent",
            system_message = system_message,
            knowledge_base = knowledge_base
        )

        from dotenv import load_dotenv
        load_dotenv()

        self.client = genai.Client(api_key = os.getenv("GEMINI_API_KEY"))

        
        self.signal = "Good"

        # Subscribe to the Pub/Sub channel for communications messages targeting
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe("channel:communications")

        # Start a background listener thread
        self.listener_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
        self.listener_thread.start()

    def listen_for_messages(self):
        # Listen continuously to the Pub/Sub channel and process messages as they arrive
        for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    logging.info(f"[Communications] Received message: {data}")

                    # Process request and update inventory as needed
                    response = self.process_request(data)
                    logging.info(f"[Communications] Processed response: {response}")

                    # Write response to the blackboard stream
                    redis_client.xadd("blackboard:updates", {"update": json.dumps(response)})
                except Exception as e:
                    logging.info(f"[Communications] Error processing message: {e}")

    def process_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        # For simplicity, assume a request might ask for a count of items
        try:
            task_type = message.get("task")
            params = message.get("parameters", {})

            if task_type == "get_signal_status":
                response = {
                    "agent": self.name,
                    "signal_status": self.signal_status
                }
            else:
                response = {"status": "error", "message": f"Unkown task: {task_type}"}

            return {
                "timestamp": str(datetime.now()),
                "task_type": task_type,
                "response": response
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }


    def run(self):
        """Main loop for the communications agent: periodically update the global blackboard."""

        while True:
            update_message = {
                "timestamp": str(datetime.now()),
                "agent": self.name,
                "signal_status": self.signal_status
            }
            redis_client.xadd("blackboard:updates", {"update": json.dumps(update_message)})
            time.sleep(60)
        

# For standalone testing or when running in a Docker container
if __name__ == "__main__":
    communications_agent = CommunicationsAgent()
    communications_agent.run()