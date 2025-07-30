# agents/logistics/logistics_chief.py

import csv
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
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Redis connection (used for both Pub/Sub and the Blackboard Stream)
# TODO: implement redis_bus.py under the utils folder
load_dotenv()
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
        # TODO: better system message/job description prompt needed 
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

        self.client = genai.Client(api_key = os.getenv("GEMINI_API_KEY"))
        self.pending_tasks = []

        self.inventory_equipment = self.load_csv("agents/inventory_equipment.csv")
        self.inventory_personnel = self.load_csv("agents/inventory_personnel.csv")
        # self.resource_snapshot = {}

        # Initialize Blackboard keys for global state
        redis_client.set("global:misson_status", "active")

        #Append to a Redis stream representing the global blackboard
        redis_client.xadd("blackboard:updates", {"update": "System initialized"})

        # Thread 1: Listen to logistics requests
        self.stream_thread = threading.Thread(target = self.listen_to_stream, daemon = True)
        self.stream_thread.start()

        # Thread 2: Pub/Sub fallback
            # Subscribe to the Pub/Sub channel for agent messages targeting the chief
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe("channel:lsc")
        self.pubsub_thread = threading.Thread(target = self.listen_for_messages, daemon = True)
        self.pubsub_thread.start()

    def load_csv(self, filepath: str) -> list:
        """Load CSV data into memory"""

        try:
            with open(filepath, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                logging.info(f"Successfully loaded {filepath}")
                return list(reader)
        except FileNotFoundError:
            logging.warning(f"Could not find file: {filepath}")
            return []
        
    def listen_to_stream(self):
        """Continuously process Redis stream logistics.requests.raw"""

        group = "logistics_group"
        consumer = self.name
        stream = "logistics.requests.raw"

        try:
            redis_client.xgroup_create(stream, group, id = '0', mkstream = True)
        except redis.exceptions.ResponseError:
            pass    # Group already exists

        while True:
            messages = redis_client.xreadgroup(group, consumer, {stream: ">"}, count = 1, block = 5000)
            
            for stream_key, entries in messages:
                for msg_id, msg_data in entries:
                    try:
                        logging.debug(f"msg_data = {msg_data}")
                        request = json.loads(msg_data["request"])
                        response = self.handle_request(request)
                        redis_client.xadd("logistics.dispatch.out", {"dispatch": json.dumps(response)})
                        redis_client.xack(stream, group, msg_id)
                    except Exception as e:
                        logging.error(f"Error handling stream message: {e}")

    # TODO: update handle_request to handle inventory_personnel as well
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Parse request and allocate resources accordingly"""

        logging.debug(f"request = {request}")

        req_type = request.get("type")
        logging.debug(f"req_type = {req_type}")
        
        quantity = int(request.get("qty", 0))
        logging.debug(f"quantity = {quantity}")

        if req_type is None or quantity <= 0:
            return {"status": "error", "message": "Invalid request format"}
        
        for item in self.inventory_equipment:
            if item["type"] == req_type:
                available = int(item["qty_available"])

                if available >= quantity:
                    item["qty_available"] = str(available - quantity) 
                    # TODO: Update quantity available in the CSV

                    return {
                        "status": "dispatched",
                        "item_type": req_type,
                        "qty": quantity,
                        "notes": item.get("notes", ""),
                        "timestamp": str(datetime.now())
                    }
                else:
                    return {
                        "status": "shortage",
                        "requested": quantity,
                        "available": available,
                        "item_type": req_type,
                        "timestamp": str(datetime.now())
                    }
        
        return {
            "status": "not_found",
            "item_type": req_type,
            "timestamp": str(datetime.now())
        }

    def listen_for_messages(self):
        """
        Fallback listener for Pub/Sub
        
        Listens continuously to the Pub/Sub channel and process messages as they arrive
        """

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
        return {
            "status": "success",
            "equipment_snapshot": self.inventory_equipment,
            "personnel_snapshot": self.inventory_personnel,
            "notes": "Snapshot retrieved"
        }

    def delegate_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        task = {
            "assigned_to": params.get("assigned_to", self.name),
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
            redis_client.xadd("blackboard:updates", {"update": json.dumps(update_message)})
            time.sleep(60)
        

# For standalone testing or when running in a Docker container
if __name__ == "__main__":
    chief = LogisticsChiefAgent()
    chief.run()