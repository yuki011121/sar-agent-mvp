# agents/health/main.py

import os
import time
import logging
import json
from datetime import datetime, timezone
from typing import Dict, List
import google.generativeai as genai
from dotenv import load_dotenv


from shared import RedisBus, wrap_envelope, parse_message_from_stream, mcp_tools

load_dotenv()

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 60))  # Check every minute
AGENT_VERSION = "health-agent-v1.0"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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

# Initialize RedisBus
try:
    bus = RedisBus(REDIS_URL)
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except Exception as e:
    logging.error(f"Could not connect to Redis via RedisBus: {e}")
    exit(1)

# Initialize Google Gemini
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    logging.warning("GOOGLE_API_KEY not set. Using mock LLM responses.")
    model = None


class HealthProfile:
    """Aggregates all health-related data for a missing person"""
    
    def __init__(self):
        self.person_info = {}
        self.weather_data = {}
        self.field_observations = []
        self.timestamp = datetime.now(timezone.utc).isoformat()
    
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


def read_latest_payloads(stream_name: str, count: int = 10) -> List[Dict]:
    """Read latest StandardMessages from a Redis stream and return their payloads.

    Expects messages published with `RedisBus` using field 'body' that contains a
    serialized `StandardMessage`. Falls back to empty list if parsing fails.
    """
    try:
        # Using the underlying bus client for a point-in-time read
        messages = bus.client.xrevrange(stream_name, count=count)
        parsed_payloads: List[Dict] = []
        for _msg_id, raw_data in messages:
            # xrevrange returns bytes as keys/values since decode_responses=False
            decoded = {
                (k.decode('utf-8') if isinstance(k, (bytes, bytearray)) else k):
                (v.decode('utf-8') if isinstance(v, (bytes, bytearray)) else v)
                for k, v in raw_data.items()
            }
            
            # Try to parse as StandardMessage first
            std_msg = parse_message_from_stream(decoded)
            if std_msg:
                parsed_payloads.append(std_msg.payload)
            else:
                # Fallback: if no 'body' field, try to use the data directly
                # This handles cases where data might be stored directly without envelope
                if 'body' not in decoded:
                    logging.warning(f"No 'body' field found in stream {stream_name}, trying direct data")
                    # Look for any field that might contain JSON data
                    for key, value in decoded.items():
                        if key not in ['__source', '__version', '__timestamp']:  # Skip metadata fields
                            try:
                                if isinstance(value, str):
                                    data = json.loads(value)
                                    parsed_payloads.append(data)
                                    break
                            except json.JSONDecodeError:
                                continue
        return parsed_payloads
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
    """Call the LLM and parse the response.

    If a Gemini API key is available, attempts tool-calling via `shared.mcp_tools` with a
    single tool `extract_health_assessment` whose arguments should match the expected
    assessment JSON. Falls back to parsing raw JSON text if no tool call is made.
    In environments without an API key, returns a deterministic mock.
    """
    if not GOOGLE_API_KEY or model is None:
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
        system_instruction = (
            "You are a medical assessment AI for search and rescue operations. "
            "Prefer calling the provided function with a structured JSON argument."
        )

        extract_assessment_tool = {
            "type": "function",
            "function": {
                "name": "extract_health_assessment",
                "description": "Return the health assessment object extracted from the provided case details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "risk_level": {
                            "type": "string",
                            "enum": ["HIGH", "MEDIUM", "LOW"]
                        },
                        "primary_health_risks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "condition": {"type": "string"},
                                    "severity": {
                                        "type": "string",
                                        "enum": ["critical", "serious", "moderate", "minor"]
                                    },
                                    "reasoning": {"type": "string"}
                                },
                                "required": ["condition", "severity", "reasoning"]
                            }
                        },
                        "recommended_actions": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "required_supplies": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "item": {"type": "string"},
                                    "quantity": {"type": "string"},
                                    "priority": {
                                        "type": "string",
                                        "enum": ["urgent", "high", "medium", "low"]
                                    }
                                },
                                "required": ["item", "quantity", "priority"]
                            }
                        },
                        "logistics_request_needed": {"type": "boolean"}
                    },
                    "required": [
                        "risk_level",
                        "primary_health_risks",
                        "recommended_actions",
                        "required_supplies",
                        "logistics_request_needed",
                    ],
                },
            },
        }

        req = mcp_tools.create_tool_use_request(
            conversation=[{"role": "user", "content": prompt}],
            tools=[extract_assessment_tool],
            system_instruction=system_instruction,
            provider="gemini",
            model=os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.0-flash"),
        )

        response = model.generate_content(**req)
        response_dict = response.to_dict()

        tool_call = mcp_tools.get_tool_call_from_response(response_dict, provider="gemini")
        if tool_call:
            name, args = tool_call
            if name == "extract_health_assessment" and isinstance(args, dict):
                return args

        # If shared parser didn't find the tool call, scan parts locally (without editing shared code)
        for cand in response_dict.get("candidates", []):
            parts = (cand.get("content", {}) or {}).get("parts", []) or []
            for part in parts:
                call = part.get("functionCall") or part.get("function_call")
                if call and call.get("name") == "extract_health_assessment":
                    args = call.get("args", {})
                    if isinstance(args, dict):
                        return args

        # Fallback: try to parse free-form JSON text without touching response.text
        try:
            candidates = response_dict.get("candidates", [])
            text_parts = []
            for cand in candidates:
                parts = (cand.get("content", {}) or {}).get("parts", []) or []
                for part in parts:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
            if text_parts:
                combined_text = "\n".join(text_parts)
                # Handle JSON wrapped in code blocks
                if "```json" in combined_text:
                    json_start = combined_text.find("```json") + 7
                    json_end = combined_text.find("```", json_start)
                    if json_end != -1:
                        combined_text = combined_text[json_start:json_end].strip()
                elif "```" in combined_text:
                    json_start = combined_text.find("```") + 3
                    json_end = combined_text.find("```", json_start)
                    if json_end != -1:
                        combined_text = combined_text[json_start:json_end].strip()
                return json.loads(combined_text)
        except Exception as e:
            logging.warning(f"JSON parsing failed: {e}")
            pass

        # If no usable text, raise to outer handler to return a safe fallback
        raise ValueError("No function call or JSON text found in Gemini response")

    except Exception as e:
        logging.error(f"Error calling LLM: {e}")
        logging.error(f"LLM error details: {type(e).__name__}: {str(e)}")
        return {
            "risk_level": "UNKNOWN",
            "primary_health_risks": [{"condition": "Unable to assess", "severity": "unknown", "reasoning": f"LLM error: {str(e)}"}],
            "recommended_actions": ["Manual assessment required"],
            "required_supplies": [],
            "logistics_request_needed": False
        }


def publish_health_assessment(assessment: Dict):
    """Publish health assessment to Redis stream via RedisBus using A2A envelope."""
    payload = {
        "metadata": {
            "agent_name": AGENT_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "assessment_type": "health_risk",
        },
        "assessment": assessment,
    }
    try:
        std_msg = wrap_envelope(
            payload=payload,
            source_name="health-agent",
            source_version=AGENT_VERSION,
            target_stream=HEALTH_ASSESSMENT_STREAM,
        )
        bus.publish(std_msg)
        logging.info(f"Published health assessment to {HEALTH_ASSESSMENT_STREAM}")
    except Exception as e:
        logging.error(f"Failed to publish health assessment: {e}")


def publish_logistics_request(assessment: Dict):
    """Publish logistics request if needed via RedisBus using A2A envelope."""
    if not assessment.get("logistics_request_needed", False):
        return

    supplies = assessment.get("required_supplies", [])
    if not supplies:
        return

    payload = {
        "metadata": {
            "agent_name": AGENT_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request_type": "medical_supplies",
        },
        "priority": "urgent" if assessment.get("risk_level") == "HIGH" else "normal",
        "supplies_needed": supplies,
        "reasoning": assessment.get("primary_health_risks", []),
    }

    try:
        std_msg = wrap_envelope(
            payload=payload,
            source_name="health-agent",
            source_version=AGENT_VERSION,
            target_stream=LOGISTICS_REQUEST_STREAM,
        )
        bus.publish(std_msg)
        logging.info(f"Published logistics request to {LOGISTICS_REQUEST_STREAM}")
    except Exception as e:
        logging.error(f"Failed to publish logistics request: {e}")


def process_health_assessment():
    """Main processing loop for health assessment"""
    health_profile = HealthProfile()
    
    # Read mission data (person info)
    mission_payloads = read_latest_payloads(MISSION_STREAM, count=1)
    logging.info(f"Read {len(mission_payloads)} mission payloads from {MISSION_STREAM}")
    if mission_payloads:
        person_info = mission_payloads[0].get("person", {})
        logging.info(f"Using mission data: {person_info}")
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
        logging.info("Using hardcoded mission data")
    health_profile.update_person_info(person_info)
    
    # Read weather data
    weather_payloads = read_latest_payloads(WEATHER_STREAM, count=1)
    if weather_payloads:
        # Extract relevant weather info
        forecasts = weather_payloads[0].get("forecasts", [])
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
    observations_payloads = read_latest_payloads(OBSERVATION_STREAM, count=5)
    if not observations_payloads:
        # Hardcoded observations for testing
        observations = [
            {
                "time": "2 hours ago",
                "report": "Found personal items (water bottle, empty)",
                "location": "2 miles from last known position"
            }
        ]
    else:
        observations = [p.get("observation", p) for p in observations_payloads]

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
