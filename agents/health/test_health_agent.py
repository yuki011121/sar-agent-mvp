#!/usr/bin/env python3
"""
Test script for the Health Agent
Publishes sample data to Redis streams to test the agent
"""

import json
import redis
import time
from datetime import datetime

# Connect to Redis
redis_client = redis.Redis.from_url("redis://localhost:6379", decode_responses=True)

def publish_mission_data():
    """Publish a sample mission with person info"""
    mission_data = {
        "metadata": {
            "agent_name": "commander-agent",
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "mission_id": "SAR-2024-001"
        },
        "person": {
            "name": "Jane Smith",
            "age": 62,
            "gender": "female",
            "known_conditions": ["diabetes type 2", "hypertension", "recent knee surgery"],
            "medications": ["metformin", "lisinopril"],
            "clothing": "red jacket, black pants, white sneakers",
            "time_missing": "48 hours",
            "last_seen": "Pine Ridge Trail, near creek crossing",
            "physical_condition": "moderate fitness, limited mobility due to knee"
        }
    }
    
    msg_id = redis_client.xadd("mission.new", {"data": json.dumps(mission_data)})
    print(f"Published mission data with ID: {msg_id}")

def publish_field_observation():
    """Publish a field observation"""
    observation_data = {
        "metadata": {
            "agent_name": "field-team-alpha",
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "location": "37.1234, -119.5678"
        },
        "observation": {
            "time": "30 minutes ago",
            "report": "Found discarded medication bottle (metformin), appears recently dropped",
            "location": "0.5 miles downstream from last known position",
            "signs": "Footprints leading toward dense vegetation, uneven gait pattern",
            "concerns": "Medication bottle suggests person may be without diabetes medication"
        }
    }
    
    msg_id = redis_client.xadd("field.observation.raw", {"data": json.dumps(observation_data)})
    print(f"Published field observation with ID: {msg_id}")

def check_health_assessment():
    """Check if health assessment was generated"""
    try:
        messages = redis_client.xrevrange("health.assessment.raw", count=1)
        if messages:
            msg_id, data = messages[0]
            assessment = json.loads(data['data'])
            print("\nLatest Health Assessment:")
            print(json.dumps(assessment, indent=2))
        else:
            print("\nNo health assessments found yet")
    except Exception as e:
        print(f"Error reading health assessment: {e}")

def check_logistics_request():
    """Check if logistics request was generated"""
    try:
        messages = redis_client.xrevrange("logistics.requests.raw", count=1)
        if messages:
            msg_id, data = messages[0]
            request = json.loads(data['data'])
            print("\nLatest Logistics Request:")
            print(json.dumps(request, indent=2))
        else:
            print("\nNo logistics requests found yet")
    except Exception as e:
        print(f"Error reading logistics request: {e}")

if __name__ == "__main__":
    print("Health Agent Test Script")
    print("========================")
    
    # Publish test data
    print("\n1. Publishing mission data...")
    publish_mission_data()
    
    print("\n2. Publishing field observation...")
    publish_field_observation()
    
    print("\n3. Waiting for health agent to process (10 seconds)...")
    time.sleep(10)
    
    # Check results
    print("\n4. Checking results...")
    check_health_assessment()
    check_logistics_request()
    
    print("\nTest complete!")
    print("\nTo see continuous updates, run:")
    print("  docker exec -it sar-agent-mvp-redis-1 redis-cli")
    print("  Then: XREVRANGE health.assessment.raw + - COUNT 5")