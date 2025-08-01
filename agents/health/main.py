# agents/health/main.py

import os
import time
import logging
import json
import redis
from datetime import datetime
from typing import Dict, List, Optional
import openai

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 60))  # Check every minute
AGENT_VERSION = "health-agent-v1.0"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Redis stream names
MISSION_STREAM = "mission.new"
WEATHER_STREAM = "weather.forecast.raw"
OBSERVATION_STREAM = "field.observation.raw"
HEALTH_ASSESSMENT_STREAM = "health.assessment.raw"
LOGISTICS_REQUEST_STREAM = "logistics.requests.raw"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Redis
try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)

# Initialize OpenAI
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY
else:
    logging.warning("OPENAI_API_KEY not set. Using mock LLM responses.")


class HealthProfile:
    """Aggregates all health-related data for a missing person"""
    
    def __init__(self):
        self.person_info = {}
        self.weather_data = {}
        self.field_observations = []
        self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def update_person_info(self, info: Dict):
        """Update basic person information from mission data"""
        self.person_info = info
    
    def update_weather(self, weather: Dict):
        """Update current weather conditions"""
        self.weather_data = weather
    
    def add_observation(self, observation: Dict):
        """Add field observation"""
        self.field_observations.append(observation)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for LLM prompt"""
        return {
            "person_info": self.person_info,
            "weather_conditions": self.weather_data,
            "field_observations": self.field_observations,
            "assessment_time": self.timestamp
        }


def read_latest_from_stream(stream_name: str, count: int = 10) -> List[Dict]:
    """Read latest messages from a Redis stream"""
    try:
        messages = redis_client.xrevrange(stream_name, count=count)
        parsed_messages = []
        for msg_id, data in messages:
            if 'data' in data:
                parsed_messages.append(json.loads(data['data']))
        return parsed_messages
    except Exception as e:
        logging.error(f"Error reading from stream {stream_name}: {e}")
        return []


def generate_llm_prompt(health_profile: HealthProfile) -> str:
    """Generate a prompt for the LLM based on health profile"""
    profile_data = health_profile.to_dict()
    
    prompt = f"""You are a medical assessment AI for search and rescue operations. Analyze the following missing person case and provide a health risk assessment.

MISSING PERSON INFORMATION:
{json.dumps(profile_data['person_info'], indent=2)}

CURRENT WEATHER CONDITIONS:
{json.dumps(profile_data['weather_conditions'], indent=2)}

FIELD OBSERVATIONS:
{json.dumps(profile_data['field_observations'], indent=2)}

Based on this information, provide a medical assessment in the following JSON format:
{{
    "risk_level": "HIGH/MEDIUM/LOW",
    "primary_health_risks": [
        {{
            "condition": "condition name",
            "severity": "critical/serious/moderate/minor",
            "reasoning": "explanation"
        }}
    ],
    "recommended_actions": [
        "specific action 1",
        "specific action 2"
    ],
    "required_supplies": [
        {{
            "item": "supply name",
            "quantity": "amount needed",
            "priority": "urgent/high/medium/low"
        }}
    ],
    "logistics_request_needed": true/false
}}

Consider factors like:
- Pre-existing medical conditions
- Weather exposure risks (hypothermia, heat exhaustion, dehydration)
- Time missing and likely physical state
- Any injuries or symptoms reported
- Age and physical condition
"""
    
    return prompt


def call_llm(prompt: str) -> Dict:
    """Call the LLM and parse the response"""
    if not OPENAI_API_KEY:
        # Mock response for testing without API key
        return {
            "risk_level": "MEDIUM",
            "primary_health_risks": [
                {
                    "condition": "Dehydration",
                    "severity": "moderate",
                    "reasoning": "Extended exposure without water source"
                }
            ],
            "recommended_actions": [
                "Locate and provide water immediately",
                "Monitor for signs of heat exhaustion"
            ],
            "required_supplies": [
                {
                    "item": "Water bottles",
                    "quantity": "6",
                    "priority": "urgent"
                }
            ],
            "logistics_request_needed": True
        }
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a medical assessment AI for search and rescue operations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        # Parse the JSON response
        content = response.choices[0].message.content
        return json.loads(content)
    
    except Exception as e:
        logging.error(f"Error calling LLM: {e}")
        # Return a safe default
        return {
            "risk_level": "UNKNOWN",
            "primary_health_risks": [{"condition": "Unable to assess", "severity": "unknown", "reasoning": "LLM error"}],
            "recommended_actions": ["Manual assessment required"],
            "required_supplies": [],
            "logistics_request_needed": False
        }


def publish_health_assessment(assessment: Dict):
    """Publish health assessment to Redis stream"""
    message = {
        "metadata": {
            "agent_name": AGENT_VERSION,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "assessment_type": "health_risk"
        },
        "assessment": assessment
    }
    
    try:
        msg_id = redis_client.xadd(HEALTH_ASSESSMENT_STREAM, {"data": json.dumps(message)})
        logging.info(f"Published health assessment to {HEALTH_ASSESSMENT_STREAM} with ID {msg_id}")
    except Exception as e:
        logging.error(f"Failed to publish health assessment: {e}")


def publish_logistics_request(assessment: Dict):
    """Publish logistics request if needed"""
    if not assessment.get("logistics_request_needed", False):
        return
    
    supplies = assessment.get("required_supplies", [])
    if not supplies:
        return
    
    message = {
        "metadata": {
            "agent_name": AGENT_VERSION,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "request_type": "medical_supplies"
        },
        "priority": "urgent" if assessment["risk_level"] == "HIGH" else "normal",
        "supplies_needed": supplies,
        "reasoning": assessment.get("primary_health_risks", [])
    }
    
    try:
        msg_id = redis_client.xadd(LOGISTICS_REQUEST_STREAM, {"data": json.dumps(message)})
        logging.info(f"Published logistics request to {LOGISTICS_REQUEST_STREAM} with ID {msg_id}")
    except Exception as e:
        logging.error(f"Failed to publish logistics request: {e}")


def process_health_assessment():
    """Main processing loop for health assessment"""
    health_profile = HealthProfile()
    
    # Read mission data (person info)
    mission_data = read_latest_from_stream(MISSION_STREAM, count=1)
    if mission_data:
        # For now, using hardcoded data as fallback
        person_info = mission_data[0].get("person", {})
    else:
        # Hardcoded example data
        person_info = {
            "name": "John Doe",
            "age": 45,
            "gender": "male",
            "known_conditions": ["diabetes type 2", "recent back injury"],
            "clothing": "light jacket, jeans, hiking boots",
            "time_missing": "36 hours",
            "last_seen": "mountain trail near summit"
        }
    health_profile.update_person_info(person_info)
    
    # Read weather data
    weather_data = read_latest_from_stream(WEATHER_STREAM, count=1)
    if weather_data:
        # Extract relevant weather info
        forecasts = weather_data[0].get("forecasts", [])
        if forecasts:
            current_weather = {
                "temperature": forecasts[0].get("temperature", 0),
                "temperature_unit": forecasts[0].get("temperature_unit", "F"),
                "wind_speed": forecasts[0].get("wind_speed", ""),
                "precipitation": forecasts[0].get("precipitation_probability", 0),
                "conditions": forecasts[0].get("short_forecast", "")
            }
            health_profile.update_weather(current_weather)
    else:
        # Hardcoded weather data
        health_profile.update_weather({
            "temperature": 45,
            "temperature_unit": "F",
            "wind_speed": "15-25 mph",
            "precipitation": 20,
            "conditions": "Cold, windy with chance of rain"
        })
    
    # Read field observations
    observations = read_latest_from_stream(OBSERVATION_STREAM, count=5)
    if not observations:
        # Hardcoded observations for testing
        observations = [
            {
                "time": "2 hours ago",
                "report": "Found personal items (water bottle, empty)",
                "location": "2 miles from last known position"
            }
        ]
    for obs in observations:
        health_profile.add_observation(obs)
    
    # Generate LLM prompt and get assessment
    prompt = generate_llm_prompt(health_profile)
    assessment = call_llm(prompt)
    
    # Publish results
    publish_health_assessment(assessment)
    publish_logistics_request(assessment)
    
    return assessment


def main():
    """Main loop for the Health Agent"""
    logging.info(f"{AGENT_VERSION} starting up. Update interval: {UPDATE_INTERVAL_SECONDS} seconds.")
    
    while True:
        logging.info("Starting new health assessment cycle.")
        
        try:
            assessment = process_health_assessment()
            logging.info(f"Health assessment complete. Risk level: {assessment.get('risk_level', 'UNKNOWN')}")
        except Exception as e:
            logging.error(f"Error in health assessment cycle: {e}")
        
        logging.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
