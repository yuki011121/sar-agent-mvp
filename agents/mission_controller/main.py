#!/usr/bin/env python3
"""
Mission Controller Agent - Event Router for SAR Operations

Listens to mission.new stream and routes mission data to appropriate agent input streams.
This is the central hub that triggers all agents to start processing a new SAR mission.
"""

import os
import time
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from shared import RedisBus, wrap_envelope, parse_message_from_stream

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = "mission-controller"
AGENT_VERSION = "mission-controller-v1.0"

# Input stream
INPUT_STREAM = "mission.new"

# Output streams - routes to various agents
OUTPUT_STREAMS = {
    "history": "history.in.raw",
    "interview": "interview.in.raw", 
    "field_observation": "field.observation.raw",
}

# Dead letter stream for failed messages
DEAD_LETTER_STREAM = "system.dead_letter"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


class MissionController:
    """
    Mission Controller routes incoming missions to appropriate agent input streams.
    
    Flow:
        mission.new -> MissionController -> history.in.raw
                                         -> interview.in.raw
                                         -> field.observation.raw
    """
    
    def __init__(self):
        self.bus = RedisBus(REDIS_URL)
        self.last_id = "0"  # Track last processed message ID
        logger.info(f"{AGENT_NAME} initialized")
    
    def parse_mission(self, raw_data: Dict) -> Optional[Dict[str, Any]]:
        """Parse and validate mission data."""
        try:
            parsed = parse_message_from_stream(raw_data)
            if parsed and hasattr(parsed, 'payload'):
                return parsed.payload
            elif isinstance(parsed, dict):
                return parsed.get('payload', parsed)
            return None
        except Exception as e:
            logger.error(f"Failed to parse mission: {e}")
            return None
    
    def create_history_query(self, mission: Dict) -> Dict:
        """Create a history RAG query from mission data."""
        person = mission.get("person", {})
        location = mission.get("location", {})
        
        query_parts = []
        
        # Build query from mission context
        if person.get("age"):
            query_parts.append(f"{person['age']} year old")
        if person.get("health_conditions"):
            query_parts.append(f"with {', '.join(person['health_conditions'])}")
        if location.get("terrain"):
            query_parts.append(f"in {location['terrain']} terrain")
        if location.get("name"):
            query_parts.append(f"near {location['name']}")
        
        query = " ".join(query_parts) if query_parts else "missing person search and rescue"
        
        return {
            "mission_id": mission.get("id", f"MISSION-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            "query": query,
            "context": {
                "mission_type": mission.get("type", "missing_person"),
                "person": person,
                "location": location
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def create_interview_request(self, mission: Dict) -> Dict:
        """Create an interview analysis request from mission data."""
        return {
            "mission_id": mission.get("id", f"MISSION-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            "request_type": "initial_assessment",
            "person": mission.get("person", {}),
            "witnesses": mission.get("witnesses", []),
            "interview_notes": mission.get("interview_notes", ""),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def create_field_observation(self, mission: Dict) -> Dict:
        """Create a field observation from mission data for health agent."""
        person = mission.get("person", {})
        location = mission.get("location", {})
        
        return {
            "mission_id": mission.get("id", f"MISSION-{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            "observation_type": "mission_start",
            "subject": {
                "name": person.get("name", "Unknown"),
                "age": person.get("age"),
                "health_conditions": person.get("health_conditions", []),
                "last_seen": person.get("last_seen", {}),
                "clothing": person.get("clothing", ""),
                "equipment": person.get("equipment", [])
            },
            "environment": {
                "location": location,
                "terrain": location.get("terrain", "unknown"),
                "coordinates": location.get("coordinates", {})
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def route_mission(self, mission: Dict):
        """Route mission data to all appropriate agent input streams."""
        mission_id = mission.get("id", "unknown")
        logger.info(f"Routing mission {mission_id} to agents...")
        
        routes = [
            ("history", self.create_history_query(mission)),
            ("interview", self.create_interview_request(mission)),
            ("field_observation", self.create_field_observation(mission)),
        ]
        
        for route_name, payload in routes:
            target_stream = OUTPUT_STREAMS[route_name]
            try:
                message = wrap_envelope(
                    payload=payload,
                    source_name=AGENT_NAME,
                    source_version=AGENT_VERSION,
                    target_stream=target_stream
                )
                self.bus.publish(message)
                logger.info(f"  ✓ Routed to {target_stream}")
            except Exception as e:
                logger.error(f"  ✗ Failed to route to {target_stream}: {e}")
                self._send_to_dead_letter(mission, route_name, str(e))
    
    def _send_to_dead_letter(self, original_data: Dict, failed_route: str, error: str):
        """Send failed messages to dead letter stream."""
        try:
            dead_letter = {
                "original_data": original_data,
                "failed_route": failed_route,
                "error": error,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": AGENT_NAME
            }
            message = wrap_envelope(
                payload=dead_letter,
                source_name=AGENT_NAME,
                source_version=AGENT_VERSION,
                target_stream=DEAD_LETTER_STREAM
            )
            self.bus.publish(message)
        except Exception as e:
            logger.error(f"Failed to send to dead letter: {e}")
    
    def process_stream(self):
        """Process new messages from mission.new stream."""
        try:
            # Read new messages (non-blocking with timeout)
            messages = self.bus._client.xread(
                {INPUT_STREAM: self.last_id},
                count=10,
                block=5000  # 5 second timeout
            )
            
            if not messages:
                return
            
            for stream_name, stream_messages in messages:
                for msg_id, data in stream_messages:
                    logger.info(f"Received mission: {msg_id}")
                    
                    mission = self.parse_mission(data)
                    if mission:
                        self.route_mission(mission)
                    else:
                        logger.warning(f"Invalid mission data: {data}")
                    
                    # Update last processed ID
                    self.last_id = msg_id
                    
        except Exception as e:
            logger.error(f"Error processing stream: {e}")
    
    def run(self):
        """Main loop."""
        logger.info(f"{AGENT_NAME} starting...")
        logger.info(f"Listening on: {INPUT_STREAM}")
        logger.info(f"Routing to: {list(OUTPUT_STREAMS.values())}")
        
        while True:
            try:
                self.process_stream()
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(5)


def main():
    controller = MissionController()
    controller.run()


if __name__ == "__main__":
    main()
