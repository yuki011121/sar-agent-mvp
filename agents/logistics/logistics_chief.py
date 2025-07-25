# agents/logistics/logistics_chief.py

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

class LogisticsChiefAgent(SARBaseAgent):
    def __init__(self, name="logistics_chief", knowledge_base=None):
        system_message = """
                         You are the Logistics Section Chief in a FEMA-aligned SAR operation.

                         You oversee supply chain operations, transportation, base camp services, and communication logistics.

                         Responsibilities:
                         - Coordinate with subordinate agents (e.g. supply, transport, comms)
                         - Prioritize requests based on mission urgency
                         - Maintain situational awareness and resource status
                         - Validate resource availability and ETA
                         - Ensure ICS compliance
                         
                         Respond with authoritative, concise, and mission-critical guidance.
                         """
        
        super().__init__(
            name = name,
            role = "Logistics Section Chief",
            system_message = system_message,
            knowledge_base = knowledge_base
        )

        from dotenv import load_dotenv
        load_dotenv()

        self.client = genai.Client(api_key = os.getenv("GEMINI_API_KEY"))
        self.pending_tasks = []
        self.resource_snapshot = {} # TODO: Will likely need to initialize this by accessing CSV file or a database

        # Initialize Blackboard keys for global state
        redis_client.set("global:misson_status", "active")

        #Append to a Redis stream representing the global blackboard
        redis_client.xadd("blackboard:updates", {"update": "System initialized"})

        # Subscribe to the Pub/Sub channel for agent messages targeting the chief
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe("channel:lsc")

        # Start a background listener thread
        self.listener_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
        self.listener_thread.start()

    def listen_for_messages(self):
        # Listen continuously to the Pub/Sub channel and process messages as they arrive
        for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    logging.info(f"[LSC Listener] Received message: {data}")

                    # Process the message through process_request
                    response = self.process_request(data)
                    logging.info(f"[LSC Listener] Processed response: {response}")

                    # Write response to the blackboard stream
                    redis_client.xadd("blackboard:updates", {"update": json.dumps(response)})
                except Exception as e:
                    logging.info(f"[LSC Listener] Error processing message: {e}")

    def process_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        try:
            task_type = message.get("task")
            params = message.get("parameters", {})

            if task_type == "review_resource_status":
                response = self.review_resource_status(params)
            elif task_type == "delegate_task":
                response = self.delegate_task(params)
            elif task_type == "get_summary":
                response = self.get_summary(params)
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
    
    def review_resource_status(self, params:Dict[str, Any]) -> Dict[str, Any]:
        # Simulated status check
        # TODO: implement a 15 minute timer for this
        return {
            "status": "success",
            "resource": self.resource_snapshot,
            "notes": "Snapshot retrieved, Update frequency: every 15 minutes."
        }

    def delegate_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        task = {
            "assigned_to": params.get("assigned_to", "logistics_section_chief"),
            "description": params.get("description", "No details"),
            "priority": params.get("priority", "Medium"),
            "timestamp": str(datetime.now())
        }

        self.pending_tasks.append(task)

        return {
            "status": "task_delegated",
            "task": task
        }
    
    def get_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "summary_ready",
            "task_count": len(self.pending_tasks),
            "latest_task": self.pending_tasks[-1] if self.pending_tasks else None
        }

    def run(self):
        """Main loop for the chief agent: periodically update the global blackboard."""

        while True:
            # Update the mission status every minute
            current_status = redis_client.get("global:mission_status")
            update_message = {
                "timestamp": str(datetime.now()),
                "mission_status": current_status,
                "pending_tasks": len(self.pending_tasks)
            }
            redis_client.xadd("blackboard:updates", {"updates": json.dumps(update_message)})
            time.sleep(60)
        

# For standalone ttesting or when running in a Docker container
if __name__ == "__main__":
    chief = LogisticsChiefAgent()
    chief.run()