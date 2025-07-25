# agents/logistics/resource_supply_agent.py

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

class ResourceSupplyAgent(SARBaseAgent):
    def __init__(self, name="resource_supply", knowledge_base=None):
        # TODO: better system message/job description prompt needed 
        system_message = """
                         You are the Resource Supply Agent in a FEMA-aligned SAR operation.

                         You are responsible for tracking and managing critical SAR resources which include but are not limited to: medical kits, batteries, fuel, food, and water.

                         Ensure that accurate inventory levels are maintained and updated
                         
                         Respond with authoritative, concise, and mission-critical guidance.
                         """
        
        super().__init__(
            name = name,
            role = "Resource Supply Agent",
            system_message = system_message,
            knowledge_base = knowledge_base
        )

        from dotenv import load_dotenv
        load_dotenv()

        self.client = genai.Client(api_key = os.getenv("GEMINI_API_KEY"))

        # TODO: inventory will likely be loaded from CSV files and databases
        # For simplicity, inventory is hard-coded for now
        self.inventory = {"Medical Kits": 50, "Fuel": 100, "Food": 200, "Water": 300}

        # Subscribe to the Pub/Sub channel for resource supply messages targeting
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe("channel:resource_supply")

        # Start a background listener thread
        self.listener_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
        self.listener_thread.start()

    def listen_for_messages(self):
        # Listen continuously to the Pub/Sub channel and process messages as they arrive
        for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    logging.info(f"[Resource Supply] Received message: {data}")

                    # Process request and update inventory as needed
                    response = self.process_request(data)
                    logging.info(f"[Resource Supply] Processed response: {response}")

                    # Write response to the blackboard stream
                    redis_client.xadd("blackboard:updates", {"update": json.dumps(response)})
                except Exception as e:
                    logging.info(f"[Resource Supply] Error processing message: {e}")

    def process_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        # For simplicity, assume a request might ask for a count of items
        try:
            task_type = message.get("task")
            params = message.get("parameters", {})

            if task_type == "get_inventory":
                response = {
                    "agent": self.name,
                    "inventory": self.inventory
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
        """Main loop for the resource supply agent: periodically update the global blackboard."""

        while True:
            update_message = {
                "timestamp": str(datetime.now()),
                "agent": self.name,
                "inventory": self.inventory
            }
            redis_client.xadd("blackboard:updates", {"update": json.dumps(update_message)})
            time.sleep(60)
        

# For standalone testing or when running in a Docker container
if __name__ == "__main__":
    supply_agent = ResourceSupplyAgent()
    supply_agent.run()