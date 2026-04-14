# agents/logistics/main.py

"""
Logistics Agent (v1.2)

Manages SAR resource inventory and responds to logistics queries.

Features:
- Loads real inventory from CSV files (equipment + personnel)
- On-demand queries via logistics.query.raw stream
- Periodic inventory status publishing
- Task ID correlation for dispatch/response pattern
"""

import os
import csv
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from shared import RedisBus, wrap_envelope

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = os.getenv("AGENT_NAME", "logistics-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "logistics-agent-v1.2")
OUTPUT_STREAM = "logistics.status.raw"
QUERY_INPUT_STREAM = "logistics.query.raw"
DEAD_LETTER_STREAM = "system.dead_letter"
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600))  # 1 hour

# Inventory file paths
EQUIPMENT_CSV = os.getenv("EQUIPMENT_CSV", "data/inventory_equipment.csv")
PERSONNEL_CSV = os.getenv("PERSONNEL_CSV", "data/inventory_personnel.csv")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


class InventoryManager:
    """Manages equipment and personnel inventory from CSV files."""
    
    def __init__(self, equipment_csv: str, personnel_csv: str):
        self.equipment: List[Dict[str, Any]] = []
        self.personnel: List[Dict[str, Any]] = []
        self._load_inventory(equipment_csv, personnel_csv)
    
    def _load_inventory(self, equipment_csv: str, personnel_csv: str):
        """Load inventory data from CSV files."""
        # Try multiple paths for equipment
        for path in [equipment_csv, f"/workspace/{equipment_csv}", f"../{equipment_csv}"]:
            if Path(path).exists():
                self.equipment = self._load_csv(path)
                logger.info(f"Loaded {len(self.equipment)} equipment items from {path}")
                break
        else:
            logger.warning(f"Equipment CSV not found: {equipment_csv}")
        
        # Try multiple paths for personnel
        for path in [personnel_csv, f"/workspace/{personnel_csv}", f"../{personnel_csv}"]:
            if Path(path).exists():
                self.personnel = self._load_csv(path)
                logger.info(f"Loaded {len(self.personnel)} personnel teams from {path}")
                break
        else:
            logger.warning(f"Personnel CSV not found: {personnel_csv}")
    
    def _load_csv(self, filepath: str) -> List[Dict[str, Any]]:
        """Load a CSV file into a list of dicts."""
        records = []
        try:
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Convert numeric fields
                    for key in ['qty_total', 'qty_available']:
                        if key in row:
                            try:
                                row[key] = int(row[key])
                            except (ValueError, TypeError):
                                pass
                    records.append(row)
        except Exception as e:
            logger.error(f"Error loading CSV {filepath}: {e}")
        return records
    
    def get_equipment_status(self) -> Dict[str, Any]:
        """Get current equipment inventory status."""
        summary = {
            "total_items": len(self.equipment),
            "categories": {},
            "low_stock": [],
            "out_of_stock": []
        }
        
        for item in self.equipment:
            category = item.get("category", "unknown")
            if category not in summary["categories"]:
                summary["categories"][category] = []
            summary["categories"][category].append(item)
            
            qty_available = item.get("qty_available", 0)
            qty_total = item.get("qty_total", 0)
            
            if qty_available == 0:
                summary["out_of_stock"].append(item)
            elif qty_total > 0 and qty_available / qty_total < 0.25:
                summary["low_stock"].append(item)
        
        return summary
    
    def get_personnel_status(self) -> Dict[str, Any]:
        """Get current personnel availability status."""
        summary = {
            "total_teams": len(self.personnel),
            "skills_available": {},
            "available_teams": [],
            "unavailable_teams": []
        }
        
        for team in self.personnel:
            skills = team.get("skills", "").split(",")
            qty = team.get("qty_available", 0)
            
            if isinstance(qty, str):
                try:
                    qty = int(qty)
                except ValueError:
                    qty = 0
            
            if qty > 0:
                summary["available_teams"].append(team)
                for skill in skills:
                    skill = skill.strip()
                    if skill:
                        if skill not in summary["skills_available"]:
                            summary["skills_available"][skill] = 0
                        summary["skills_available"][skill] += qty
            else:
                summary["unavailable_teams"].append(team)
        
        return summary
    
    def search_equipment(self, query: str) -> List[Dict[str, Any]]:
        """Search equipment by type, category, or item_id."""
        query_lower = query.lower()
        results = []
        
        for item in self.equipment:
            if (query_lower in item.get("type", "").lower() or
                query_lower in item.get("category", "").lower() or
                query_lower in item.get("item_id", "").lower() or
                query_lower in item.get("notes", "").lower()):
                results.append(item)
        
        return results
    
    def search_personnel(self, skill: str) -> List[Dict[str, Any]]:
        """Search personnel teams by skill."""
        skill_lower = skill.lower()
        results = []
        
        for team in self.personnel:
            skills = team.get("skills", "").lower()
            if skill_lower in skills:
                results.append(team)
        
        return results
    
    def get_full_inventory(self) -> Dict[str, Any]:
        """Get complete inventory data."""
        return {
            "equipment": {
                "items": self.equipment,
                "status": self.get_equipment_status()
            },
            "personnel": {
                "teams": self.personnel,
                "status": self.get_personnel_status()
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def process_query(self, query: str, query_type: Optional[str] = None) -> Dict[str, Any]:
        """Process a logistics query and return results."""
        results = {}
        
        query_type = query_type or "all"
        query_lower = query.lower()
        
        # Determine what to search
        if query_type in ["equipment", "all"]:
            results["equipment"] = self.search_equipment(query)
        
        if query_type in ["personnel", "all"]:
            results["personnel"] = self.search_personnel(query)
        
        # Special queries
        if "status" in query_lower or "inventory" in query_lower:
            results["equipment_status"] = self.get_equipment_status()
            results["personnel_status"] = self.get_personnel_status()
        
        if "available" in query_lower:
            results["available_equipment"] = [
                item for item in self.equipment 
                if item.get("qty_available", 0) > 0
            ]
            results["available_personnel"] = [
                team for team in self.personnel 
                if team.get("qty_available", 0) > 0
            ]
        
        return results


def publish_inventory_status(bus: RedisBus, inventory: InventoryManager, 
                             task_id: Optional[str] = None):
    """Publish current inventory status to Redis stream."""
    try:
        payload = inventory.get_full_inventory()
        payload["agent_name"] = AGENT_NAME
        payload["agent_version"] = AGENT_VERSION
        
        if task_id:
            payload["task_id"] = task_id
        
        message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=OUTPUT_STREAM
        )
        bus.publish(message)
        logger.info(f"Published inventory status to '{OUTPUT_STREAM}'" +
                   (f" (task_id: {task_id})" if task_id else ""))
                   
    except Exception as e:
        logger.error(f"Failed to publish inventory status: {e}")
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": "Failed while publishing inventory status"
        }
        if task_id:
            error_payload["task_id"] = task_id
            
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM
        )
        bus.publish(error_message)


def publish_query_result(bus: RedisBus, inventory: InventoryManager,
                         query: str, query_type: Optional[str] = None,
                         task_id: Optional[str] = None,
                         mission_id: Optional[str] = None):
    """Process and publish query results."""
    try:
        results = inventory.process_query(query, query_type)
        
        payload = {
            "query": query,
            "query_type": query_type,
            "results": results,
            "agent_name": AGENT_NAME,
            "agent_version": AGENT_VERSION,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if task_id:
            payload["task_id"] = task_id
        if mission_id:
            payload["mission_id"] = mission_id
        
        message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=OUTPUT_STREAM
        )
        bus.publish(message)
        logger.info(f"Published query result to '{OUTPUT_STREAM}'" +
                   (f" (task_id: {task_id})" if task_id else ""))
                   
    except Exception as e:
        logger.error(f"Failed to process query: {e}")
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": f"Failed while processing query: {query}"
        }
        if task_id:
            error_payload["task_id"] = task_id
            
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM
        )
        bus.publish(error_message)


def periodic_publisher(bus: RedisBus, inventory: InventoryManager):
    """Background thread for periodic inventory publishing."""
    logger.info(f"Periodic publisher started. Interval: {UPDATE_INTERVAL_SECONDS}s")
    while True:
        logger.info("Starting periodic inventory status cycle.")
        publish_inventory_status(bus, inventory)
        logger.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


def query_listener(bus: RedisBus, inventory: InventoryManager):
    """Listen for on-demand logistics queries via logistics.query.raw stream."""
    logger.info(f"Query listener started. Listening on: {QUERY_INPUT_STREAM}")
    
    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-query-group",
            consumer_name=f"{AGENT_NAME}-query-consumer",
            streams=[QUERY_INPUT_STREAM],
            block_ms=5000
        ):
            try:
                payload = message.payload
                logger.info(f"Received logistics query: {payload}")
                
                # Extract parameters
                task_id = payload.get("task_id")
                mission_id = payload.get("mission_id")
                query = payload.get("query", "status")
                query_type = payload.get("query_type")  # equipment, personnel, or all
                
                if query == "status" or query == "inventory":
                    # Full inventory status
                    publish_inventory_status(bus, inventory, task_id=task_id)
                else:
                    # Search query
                    publish_query_result(
                        bus, inventory,
                        query=query,
                        query_type=query_type,
                        task_id=task_id,
                        mission_id=mission_id
                    )
                
            except Exception as e:
                logger.error(f"Error processing query message: {e}")
                
    except Exception as e:
        logger.error(f"Query listener error: {e}")


def main():
    """Main function for the Logistics Agent."""
    logger.info(f"Initializing {AGENT_NAME} v{AGENT_VERSION}...")

    # Initialize Redis connection
    try:
        bus = RedisBus(REDIS_URL)
        logger.info(f"Successfully connected to Redis at {REDIS_URL}")
    except Exception as e:
        logger.critical(f"Could not connect to Redis: {e}")
        return

    # Load inventory from CSV files
    inventory = InventoryManager(EQUIPMENT_CSV, PERSONNEL_CSV)
    
    logger.info(f"{AGENT_NAME} starting up.")
    
    # Start periodic publisher in background thread
    periodic_thread = threading.Thread(
        target=periodic_publisher, 
        args=(bus, inventory), 
        daemon=True
    )
    periodic_thread.start()
    
    # Run query listener in main thread
    query_listener(bus, inventory)


if __name__ == "__main__":
    main()