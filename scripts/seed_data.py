#!/usr/bin/env python3
"""
SAR System Data Seeder

This script populates Redis streams with test data to enable local development
and testing without requiring all agents to be running.

Usage:
    # Seed with default sample mission
    python scripts/seed_data.py
    
    # Seed with specific mission file
    python scripts/seed_data.py --mission data/sample_missions/mission_001_missing_elderly.json
    
    # Clear existing data before seeding
    python scripts/seed_data.py --clear
    
    # Seed and run a test query
    python scripts/seed_data.py --test-query "What are the health risks?"
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis

# Try to import shared package, fall back to manual implementation
try:
    from shared import wrap_envelope, RedisBus
    HAS_SHARED = True
except ImportError:
    HAS_SHARED = False
    print("Warning: shared package not available, using manual envelope wrapping")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = "seed-data-script"
AGENT_VERSION = "1.0"

# Stream names
STREAMS = {
    "mission": "mission.new",
    "weather": "weather.forecast.raw",
    "health": "health.assessment.raw",
    "history": "history.out.raw",
    "logistics": "logistics.requests.raw",
    "path": "path.analysis.raw",
    "photo": "photo.analysis.raw",
    "interview": "interview.analysis.raw",
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_redis_client() -> redis.Redis:
    """Create Redis client."""
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


def wrap_message(payload: Dict[str, Any], target_stream: str) -> Dict[str, str]:
    """Wrap payload in standard message envelope."""
    if HAS_SHARED:
        msg = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=target_stream
        )
        # Use model_dump_json() for Pydantic v2
        return {"body": msg.model_dump_json()}
    else:
        # Manual envelope for when shared package isn't available
        envelope = {
            "source": {
                "name": AGENT_NAME,
                "version": AGENT_VERSION
            },
            "target_stream": target_stream,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }
        return {"body": json.dumps(envelope)}


def publish_to_stream(client: redis.Redis, stream: str, payload: Dict[str, Any]):
    """Publish payload to Redis stream."""
    fields = wrap_message(payload, stream)
    msg_id = client.xadd(stream, fields)
    logger.info(f"Published to {stream}: {msg_id}")
    return msg_id


def generate_weather_data(mission: Dict) -> Dict[str, Any]:
    """Generate synthetic weather data based on mission location."""
    location = mission.get("location", {})
    coords = location.get("coordinates", {"lat": 35.78, "lon": -120.43})
    weather_concerns = mission.get("weather_concerns", [])
    
    return {
        "source_api": "seed-data (synthetic)",
        "location": {
            "latitude": coords.get("lat", 35.78),
            "longitude": coords.get("lon", -120.43),
            "name": location.get("name", "Unknown Location")
        },
        "current_conditions": {
            "temperature_f": 48,
            "temperature_c": 9,
            "wind_speed_mph": 12,
            "wind_direction": "NW",
            "humidity_percent": 65,
            "visibility_miles": 8,
            "precipitation": "light rain" if "rain" in str(weather_concerns).lower() else "none",
            "conditions": "Partly cloudy with cooling temperatures"
        },
        "forecasts": [
            {
                "name": "Tonight",
                "temperature": 38,
                "temperatureUnit": "F",
                "shortForecast": "Mostly Cloudy, Temperature dropping",
                "detailedForecast": "Temperatures expected to drop to near freezing overnight. Light wind from the northwest around 10 mph. Visibility may be reduced in valleys."
            },
            {
                "name": "Tomorrow",
                "temperature": 52,
                "temperatureUnit": "F",
                "shortForecast": "Partly Sunny",
                "detailedForecast": "Improving conditions with partly sunny skies. High near 52F. Northwest wind 5 to 10 mph."
            }
        ],
        "sar_impact": {
            "search_conditions": "Moderate - visibility adequate for daytime operations",
            "exposure_risk": "HIGH - overnight temperatures near freezing pose hypothermia risk",
            "recommended_actions": [
                "Prioritize search before nightfall",
                "Ensure rescue teams have cold weather gear",
                "Consider thermal imaging for night operations"
            ]
        },
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


def generate_health_assessment(mission: Dict) -> Dict[str, Any]:
    """Generate health risk assessment based on mission person info."""
    person = mission.get("person", {})
    health_conditions = person.get("health_conditions", [])
    age = person.get("age", 65)
    
    # Calculate risk level based on factors
    risk_factors = []
    risk_level = "MODERATE"
    
    if age >= 70:
        risk_factors.append(f"Advanced age ({age} years) increases vulnerability")
        risk_level = "HIGH"
    elif age >= 60:
        risk_factors.append(f"Senior age ({age} years) is a concern")
    
    if "diabetes" in [c.lower() for c in health_conditions]:
        risk_factors.append("Diabetes requires regular insulin/medication - critical if not available")
        risk_level = "HIGH"
    
    if "dementia" in str(health_conditions).lower():
        risk_factors.append("Cognitive impairment affects decision-making and self-rescue ability")
        risk_level = "CRITICAL"
    
    last_seen = person.get("last_seen", {})
    last_seen_time = last_seen.get("time", "")
    
    return {
        "subject_profile": {
            "name": person.get("name", "Unknown"),
            "age": age,
            "gender": person.get("gender", "unknown"),
            "health_conditions": health_conditions,
            "medications": person.get("medications", []),
            "mobility": person.get("mobility", "unknown"),
            "clothing": person.get("clothing", "unknown")
        },
        "risk_assessment": {
            "overall_risk_level": risk_level,
            "risk_factors": risk_factors,
            "time_critical_concerns": [
                "Medication availability (insulin if diabetic)",
                "Hypothermia risk increases significantly after sunset",
                "Dehydration if water not available"
            ],
            "survival_considerations": {
                "estimated_survival_probability": "Moderate to Good if found within 24 hours",
                "critical_window": "First 24-48 hours crucial for positive outcome"
            }
        },
        "medical_recommendations": [
            "Alert medical teams for potential diabetic emergency",
            "Prepare for hypothermia treatment",
            "Have blood glucose monitoring equipment ready",
            "Brief rescue teams on subject's cognitive status"
        ],
        "search_prioritization": {
            "urgency": risk_level,
            "priority_factors": risk_factors,
            "recommended_approach": "High-intensity search with medical support on standby"
        },
        "last_seen_info": last_seen,
        "assessment_timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_history_data(mission: Dict) -> Dict[str, Any]:
    """Generate historical case analysis based on mission profile."""
    person = mission.get("person", {})
    location = mission.get("location", {})
    terrain = location.get("terrain", "unknown")
    age = person.get("age", 65)
    
    similar_cases = []
    
    if age >= 65:
        similar_cases.append({
            "case_id": "ISRID-2019-4523",
            "summary": "72-year-old male, diabetic, missing in forested area for 22 hours",
            "outcome": "Found alive, 2.3km from last seen location, mild hypothermia",
            "key_insights": [
                "Subject followed water source downhill",
                "Found near natural shelter (large fallen tree)",
                "Rescue dogs most effective search method"
            ],
            "relevance_score": 0.87
        })
    
    if "forest" in terrain.lower() or "mountain" in terrain.lower():
        similar_cases.append({
            "case_id": "ISRID-2021-1892",
            "summary": "68-year-old with dementia, mountainous terrain, 18 hours missing",
            "outcome": "Found deceased, had fallen into ravine",
            "key_insights": [
                "Terrain hazards were primary cause",
                "Subject moved uphill despite expectations",
                "Cell phone ping was misleading due to terrain"
            ],
            "relevance_score": 0.75
        })
    
    similar_cases.append({
        "case_id": "ISRID-2023-0892",
        "summary": "Similar demographic profile, temperate forest region",
        "outcome": "Found alive within 12 hours using hasty search",
        "key_insights": [
            "Early deployment of hasty teams was crucial",
            "Subject stayed near trail system",
            "Behavioral analysis predicted location accurately"
        ],
        "relevance_score": 0.72
    })
    
    return {
        "query_context": {
            "subject_age": age,
            "terrain_type": terrain,
            "conditions": person.get("health_conditions", [])
        },
        "similar_cases": similar_cases,
        "statistical_insights": {
            "similar_case_count": len(similar_cases),
            "average_find_time_hours": 18.5,
            "survival_rate": "73% for similar profiles",
            "common_find_locations": [
                "Near water sources (35%)",
                "Along trail systems (28%)",
                "Natural shelters (18%)",
                "Opposite direction from expected (12%)"
            ]
        },
        "strategic_recommendations": [
            "Deploy hasty teams along trails and water courses first",
            "Check natural shelters within 3km radius",
            "Consider uphill movement despite expected downhill travel",
            "Use canine units for dense vegetation areas"
        ],
        "generated_at": datetime.now(timezone.utc).isoformat()
    }


def generate_logistics_data(mission: Dict) -> Dict[str, Any]:
    """Generate logistics/resource data."""
    return {
        "resource_status": {
            "personnel": {
                "ground_searchers": 12,
                "k9_teams": 2,
                "medical_personnel": 3,
                "coordinators": 2
            },
            "equipment": {
                "radios": {"available": 15, "deployed": 8},
                "gps_units": {"available": 10, "deployed": 6},
                "first_aid_kits": {"available": 8, "deployed": 4},
                "night_vision": {"available": 2, "deployed": 0},
                "thermal_cameras": {"available": 1, "deployed": 0}
            },
            "vehicles": {
                "atvs": {"available": 3, "deployed": 1},
                "command_vehicles": {"available": 1, "deployed": 1}
            }
        },
        "deployment_recommendations": [
            "Deploy night vision equipment before sunset",
            "Request additional K9 teams for expanded search area",
            "Position medical team at staging area"
        ],
        "constraints": [
            "Limited night search capability",
            "ATV access restricted in some terrain"
        ],
        "status_timestamp": datetime.now(timezone.utc).isoformat()
    }


def generate_path_analysis(mission: Dict) -> Dict[str, Any]:
    """Generate terrain/path analysis data."""
    location = mission.get("location", {})
    coords = location.get("coordinates", {"lat": 35.78, "lon": -120.43})
    
    return {
        "search_area": {
            "center": coords,
            "radius_km": location.get("search_radius_km", 5),
            "terrain_type": location.get("terrain", "unknown"),
            "elevation_range_m": location.get("elevation_range_m", [800, 1500])
        },
        "terrain_assessment": {
            "difficulty": "Moderate to Difficult",
            "accessibility": {
                "vehicle": "Limited to main trails",
                "foot": "Full access with caution",
                "helicopter": "Suitable for observation, limited LZ"
            },
            "hazards": location.get("hazards", ["steep terrain", "dense brush"])
        },
        "recommended_search_routes": [
            {
                "name": "Primary Trail System",
                "priority": 1,
                "rationale": "Most likely travel corridor, easiest terrain"
            },
            {
                "name": "Creek/Water Drainage",  
                "priority": 2,
                "rationale": "Natural travel path, water source attraction"
            },
            {
                "name": "Ridge Lines",
                "priority": 3,
                "rationale": "Visibility advantage, but more difficult terrain"
            }
        ],
        "search_segment_recommendations": [
            "Focus initial hasty search on high-probability trail segments",
            "Deploy grid search in manageable terrain sections",
            "Use attraction methods (calling, lights) in evening hours"
        ],
        "analysis_timestamp": datetime.now(timezone.utc).isoformat()
    }


def clear_streams(client: redis.Redis):
    """Clear all SAR-related streams."""
    logger.info("Clearing existing streams...")
    for name, stream in STREAMS.items():
        try:
            client.delete(stream)
            logger.info(f"Cleared {stream}")
        except Exception as e:
            logger.warning(f"Could not clear {stream}: {e}")


def seed_from_mission(client: redis.Redis, mission: Dict, include_outputs: bool = True):
    """Seed Redis with data based on a mission definition."""
    
    # 1. Publish mission to mission.new
    logger.info("Seeding mission data...")
    publish_to_stream(client, STREAMS["mission"], mission)
    
    if not include_outputs:
        logger.info("Skipping agent outputs (--mission-only mode)")
        return
    
    # 2. Generate and publish synthetic agent outputs
    logger.info("Generating synthetic agent outputs...")
    
    # Weather
    weather_data = generate_weather_data(mission)
    publish_to_stream(client, STREAMS["weather"], weather_data)
    
    # Health Assessment
    health_data = generate_health_assessment(mission)
    publish_to_stream(client, STREAMS["health"], health_data)
    
    # Historical Cases
    history_data = generate_history_data(mission)
    publish_to_stream(client, STREAMS["history"], history_data)
    
    # Logistics
    logistics_data = generate_logistics_data(mission)
    publish_to_stream(client, STREAMS["logistics"], logistics_data)
    
    # Path Analysis
    path_data = generate_path_analysis(mission)
    publish_to_stream(client, STREAMS["path"], path_data)
    
    logger.info("Seeding complete!")


def load_mission_file(filepath: str) -> Dict:
    """Load mission from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def run_test_query(query: str):
    """Run a test query through the Command Agent."""
    logger.info(f"Running test query: {query}")
    try:
        from agents.command_agent.graph import run_query
        result = run_query(query, verbose=True)
        print("\n" + "="*60)
        print("TEST QUERY RESULT")
        print("="*60)
        print(result[:2000])
        if len(result) > 2000:
            print(f"\n... ({len(result) - 2000} more characters)")
    except ImportError as e:
        logger.error(f"Could not import Command Agent: {e}")
        logger.info("Make sure you've installed the dependencies:")
        logger.info("  pip install langchain-core langchain-google-genai langgraph")


def main():
    parser = argparse.ArgumentParser(description="Seed SAR system with test data")
    parser.add_argument(
        "--mission", "-m",
        default="data/sample_missions/mission_001_missing_elderly.json",
        help="Path to mission JSON file"
    )
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear existing streams before seeding"
    )
    parser.add_argument(
        "--mission-only",
        action="store_true",
        help="Only publish mission, don't generate synthetic agent outputs"
    )
    parser.add_argument(
        "--test-query", "-q",
        type=str,
        help="Run a test query after seeding"
    )
    parser.add_argument(
        "--list-streams",
        action="store_true",
        help="List all SAR streams and their message counts"
    )
    
    args = parser.parse_args()
    
    # Connect to Redis
    try:
        client = get_redis_client()
        client.ping()
        logger.info(f"Connected to Redis at {REDIS_URL}")
    except Exception as e:
        logger.error(f"Could not connect to Redis: {e}")
        logger.info("Make sure Redis is running: docker compose up -d redis")
        sys.exit(1)
    
    # List streams mode
    if args.list_streams:
        print("\nSAR Redis Streams:")
        print("-" * 50)
        for name, stream in STREAMS.items():
            try:
                length = client.xlen(stream)
                print(f"  {stream:30} : {length} messages")
            except:
                print(f"  {stream:30} : (not found)")
        return
    
    # Clear if requested
    if args.clear:
        clear_streams(client)
    
    # Load and seed mission
    mission_path = args.mission
    if not os.path.exists(mission_path):
        # Try relative to script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        mission_path = os.path.join(project_root, args.mission)
    
    if not os.path.exists(mission_path):
        logger.error(f"Mission file not found: {args.mission}")
        logger.info("Available sample missions:")
        sample_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                   "data/sample_missions")
        if os.path.exists(sample_dir):
            for f in os.listdir(sample_dir):
                if f.endswith('.json'):
                    print(f"  data/sample_missions/{f}")
        sys.exit(1)
    
    logger.info(f"Loading mission from: {mission_path}")
    mission = load_mission_file(mission_path)
    
    seed_from_mission(client, mission, include_outputs=not args.mission_only)
    
    # Verify seeding
    print("\nStream Status After Seeding:")
    print("-" * 50)
    for name, stream in STREAMS.items():
        try:
            length = client.xlen(stream)
            print(f"  {stream:30} : {length} messages")
        except:
            print(f"  {stream:30} : (error)")
    
    # Run test query if requested
    if args.test_query:
        print()
        run_test_query(args.test_query)


if __name__ == "__main__":
    main()
