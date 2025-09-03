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

load_dotenv()

# Initialize Redis connection
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

        # Initialize Blackboard keys for global state
        redis_client.set("global:mission_status", "active")

        #Append to a Redis stream representing the global blackboard
        redis_client.xadd("blackboard:updates", {"update": "System initialized"})

        # Listen to logistics requests using a background listener thread
        self.stream_thread = threading.Thread(target = self.listen_to_stream, daemon = True)
        self.stream_thread.start()

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
        
    def save_csv(self, filepath: str, data: list) -> None:
        """Writes updated inventory back to the CSV file."""

        if not data:
            logging.error(f"Attempted to write empty data to CSV")
            return

        with open(filepath, mode='w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            logging.info(f"Successfully wrote updated data to {filepath}")
        
    def listen_to_stream(self) -> None:
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


    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Main router between equipment and personnel requests"""

        logging.debug(f"[handle_request] request = {request}")

        req_type = request.get("type")
        logging.debug(f"req_type = {req_type}")
        
        if req_type == "equipment":
            return self.handle_equipment_request(request)
        elif req_type == "personnel":
            return self.handle_personnel_request(request)
        else:
            return {"status": "error", "message": f"Unknown request type: {req_type}"}
        
    def handle_equipment_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_item_type = request.get("item_type")
        logging.debug(f"req_item_type = {req_item_type}")
        
        quantity = int(request.get("qty", 0))
        logging.debug(f"quantity = {quantity}")

        if req_item_type is None or quantity <= 0:
            return {"status": "error", "message": "Invalid equipment request"}
        
        for item in self.inventory_equipment:
            if item["type"] == req_item_type:
                available = int(item["qty_available"])

                if available >= quantity:
                    item["qty_available"] = str(available - quantity) 

                    self.save_csv("agents/inventory_equipment.csv", self.inventory_equipment)

                    return {
                        "status": "dispatched",
                        "category": "equipment",
                        "item_type": req_item_type,
                        "qty": quantity,
                        "notes": item.get("notes", ""),
                        "timestamp": str(datetime.now())
                    }
                else:
                    return {
                        "status": "shortage",
                        "category": "equipment",
                        "requested": quantity,
                        "available": available,
                        "item_type": req_item_type,
                        "timestamp": str(datetime.now())
                    }
        
        return {
            "status": "not_found",
            "category": "equipment",
            "item_type": req_item_type,
            "timestamp": str(datetime.now())
        }

    def handle_personnel_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_skill = request.get("skill")
        logging.debug(f"req_skill = {req_skill}")
        
        quantity = int(request.get("qty", 0))
        logging.debug(f"quantity = {quantity}")

        if req_skill is None or quantity <= 0:
            return {"status": "error", "message": "Invalid personnel request"}

        matching_teams = []
        for team in self.inventory_personnel:
            logging.debug(f"team = {team}")

            skills = [s.strip() for s in team["skills"].split(",")]
            logging.debug(f"skills = {skills}")

            available = int(team["qty_available"])
            logging.debug(f"available = {available}")
            # TODO: error check if available is negative in the case of bad data

            if req_skill in skills and available > 0:
                matching_teams.append((team, available))

        if not matching_teams:
            return {
                "status": "not_found",
                "category": "personnel",
                "skill": req_skill,
                "timestamp": str(datetime.now())
            }
        
        total_allocated = 0
        dispatched_teams = []

        for team, available in matching_teams:
            allocate = min(quantity - total_allocated, available)
            logging.debug(f"allocate = {allocate}")
            
            team["qty_available"] = str(available - allocate)
            dispatched_teams.append(team["team_id"])
            total_allocated += allocate

            if total_allocated >= quantity:
                break

        self.save_csv("agents/inventory_personnel.csv", self.inventory_personnel)

        if total_allocated < quantity:
            return {
                "status": "partial_dispatch",
                "category": "personnel",
                "skill": req_skill,
                "dispatched_qty": total_allocated,
                "requested_qty": quantity,
                "teams": dispatched_teams,
                "timestamp": str(datetime.now())
            }
        
        return {
            "status": "dispatched",
            "category": "personnel",
            "skill": req_skill,
            "dispatched_qty": total_allocated,
            "teams": dispatched_teams,
            "timestamp": str(datetime.now())           
        }
        

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
    
    def review_resource_status(self) -> Dict[str, Any]:
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