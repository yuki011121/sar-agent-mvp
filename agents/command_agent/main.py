#!/usr/bin/env python3
"""
Command Agent - SAR System Commander
Using legacy AutoGen (pyautogen < 0.3) for multi-agent orchestration
"""

import os
import json
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("command-agent-v1.0")

# AutoGen imports
try:
    import autogen
    from autogen import ConversableAgent, UserProxyAgent, GroupChat, GroupChatManager
    AUTOGEN_AVAILABLE = True
    logger.info("✓ AutoGen imported successfully")
except ImportError as e:
    AUTOGEN_AVAILABLE = False
    logger.error(f"✗ AutoGen import failed: {e}")

from shared import RedisBus, wrap_envelope, parse_message_from_stream
import redis
import json

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AGENT_VERSION = "command-agent-v1.0"

redis_client = None
config_list = [
    {
        "model": "gpt-4",
        "api_key": OPENAI_API_KEY,
        "temperature": 0.7,
        "timeout": 120
    }
]

llm_config = {
    "config_list": config_list,
    "temperature": 0.7,
    "timeout": 120
}


class RedisTool:
    """Redis data reading tool"""
    
    def __init__(self, redis_url: str):
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.bus = RedisBus(redis_url)
        self.client.ping()
        logger.info("✓ Redis connected")
    
    def get_latest_message(self, stream_name: str) -> Dict:
        """Get latest message"""
        try:
            messages = self.client.xrevrange(stream_name, count=1)
            if messages:
                msg_id, data = messages[0]
                parsed = parse_message_from_stream(data)
                return parsed
            return {}
        except Exception as e:
            logger.error(f"Error reading {stream_name}: {e}")
            return {}
    
    def get_messages(self, stream_name: str, count: int = 10) -> List[Dict]:
        """Get multiple messages"""
        try:
            messages = self.client.xrevrange(stream_name, count=count)
            results = []
            for msg_id, data in messages:
                parsed = parse_message_from_stream(data)
                if parsed:
                    results.append(parsed)
            return results
        except Exception as e:
            logger.error(f"Error reading {stream_name}: {e}")
            return []


def get_redis_data(stream_name: str) -> str:
    """Tool function to read latest message from Redis stream"""
    global redis_client
    if not redis_client:
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    
    try:
        messages = redis_client.xrevrange(stream_name, count=5)
        if not messages:
            return f"No data found in {stream_name}"
        
        results = []
        for msg_id, data in messages:
            try:
                # Try to parse using shared module
                parsed = parse_message_from_stream(data)
                if parsed:
                    # Extract the actual payload content
                    result_data = {}
                    
                    # Check if it's a StandardMessage with payload attribute
                    if hasattr(parsed, 'payload'):
                        result_data = parsed.payload  # This is the actual weather data!
                    elif isinstance(parsed, dict):
                        # Check if it has a payload key
                        if 'payload' in parsed:
                            result_data = parsed['payload']
                        else:
                            result_data = parsed
                    else:
                        # Handle other objects
                        result_data = parsed.model_dump() if hasattr(parsed, 'model_dump') else str(parsed)
                    
                    results.append({
                        "id": msg_id,
                        "data": result_data
                    })
            except Exception as parse_error:
                # Try direct JSON parse of the raw data
                try:
                    if 'body' in data:
                        body_content = data.get('body', '{}')
                        if isinstance(body_content, str):
                            body_json = json.loads(body_content)
                            if 'payload' in body_json:
                                result_data = body_json['payload']
                            else:
                                result_data = body_json
                        else:
                            result_data = body_content
                    else:
                        result_data = data
                    
                    results.append({
                        "id": msg_id,
                        "data": result_data
                    })
                except:
                    results.append({
                        "id": msg_id,
                        "data": {"raw": data, "parse_error": str(parse_error)}
                    })
        
        return json.dumps(results, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error reading {stream_name}: {str(e)}"


class CommandAgent:
    """
    Command Agent - SAR System Commander
    Uses AutoGen to coordinate all specialist agents
    """
    
    def __init__(self):
        global redis_client
        if not AUTOGEN_AVAILABLE:
            raise ImportError("AutoGen is required. Install with: pip install pyautogen")
        
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self.redis_tool = RedisTool(REDIS_URL)
        logger.info("Command Agent initialized")
        
        self.agents = self._create_specialist_agents()
        
        self.group_chat = GroupChat(
            agents=self.agents,
            messages=[],
            max_round=50
        )
        
        self.manager = GroupChatManager(
            groupchat=self.group_chat,
            llm_config=llm_config
        )
        
        logger.info("✓ Command Agent setup complete")
    
    def _create_specialist_agents(self) -> List[ConversableAgent]:
        """Create specialist agents"""
        
        agents = []
        
        weather_agent = ConversableAgent(
            name="weather_specialist",
            system_message="""
            You are a weather analysis specialist focused on analyzing weather impact on search and rescue operations.
            
            Your responsibilities:
            1. Call get_weather_data() function to read weather data from Redis
            2. Analyze weather data (temperature, wind speed, visibility, precipitation, etc.)
            3. Assess weather conditions' impact on search operations
            4. Provide specific action recommendations (e.g., postpone search during rain, or take precautions in cold temperatures)
            
            When asked about weather, first call get_weather_data() to get the latest data, then analyze.
            Provide clear, actionable recommendations.
            """,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            function_map={
                "get_weather_data": lambda: get_redis_data("weather.forecast.raw")
            }
        )
        agents.append(weather_agent)
        
        history_agent = ConversableAgent(
            name="history_specialist",
            system_message="""
            You are a historical case analysis specialist, skilled at extracting useful information from historical SAR cases.
            
            Your responsibilities:
            1. Call get_history_data() function to read historical cases from Redis
            2. Analyze historical SAR case patterns
            3. Identify similar cases and successful strategies
            4. Provide recommendations based on historical data
            
            When asked about historical cases, first call get_history_data() to get the latest data, then analyze.
            Provide strategic recommendations based on historical data.
            """,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            function_map={
                "get_history_data": lambda: get_redis_data("history.out.raw")
            }
        )
        agents.append(history_agent)
        
        photo_agent = ConversableAgent(
            name="photo_specialist",
            system_message="""
            You are a photo analysis specialist who analyzes SAR-related image information.
            
            Your responsibilities:
            1. Call get_photo_data() function to read photo analysis results from Redis
            2. Analyze object detection results in photos
            3. Identify personnel and SAR-related items
            4. Provide search area recommendations
            
            When asked about photo analysis, first call get_photo_data() to get the latest data, then analyze.
            Provide search recommendations based on photo analysis.
            """,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            function_map={
                "get_photo_data": lambda: get_redis_data("photo.analysis.raw")
            }
        )
        agents.append(photo_agent)
        
        path_agent = ConversableAgent(
            name="path_specialist",
            system_message="""
            You are a path planning specialist who analyzes terrain and suggests search paths.
            
            Your responsibilities:
            1. Call get_path_data() function to read path analysis data from Redis
            2. Analyze terrain and path data
            3. Recommend optimal search paths
            4. Consider terrain difficulty and accessibility
            
            When asked about path planning, first call get_path_data() to get the latest data, then analyze.
            Provide specific path planning recommendations.
            """,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            function_map={
                "get_path_data": lambda: get_redis_data("path.analysis.raw")
            }
        )
        agents.append(path_agent)
        
        health_agent = ConversableAgent(
            name="health_specialist",
            system_message="""
            You are a health assessment specialist who evaluates health risks for missing persons.
            
            Your responsibilities:
            1. Call get_health_data() function to read health assessment data from Redis
            2. Assess risks based on missing person's health status and time
            3. Consider factors like age and medical history
            4. Provide health-related action recommendations
            
            When asked about health assessment, first call get_health_data() to get the latest data, then analyze.
            Provide clear health risk assessments and recommendations.
            """,
            llm_config=llm_config,
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            function_map={
                "get_health_data": lambda: get_redis_data("health.assessment.raw")
            }
        )
        agents.append(health_agent)
        
        logger.info(f"Created {len(agents)} specialist agents")
        return agents
    
    def chat(self, user_message: str):
        """Handle user message"""
        logger.info(f"User message: {user_message}")
        
        user_proxy = UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            llm_config=False,
            code_execution_config=False
        )
        
        chat_result = user_proxy.initiate_chat(
            self.manager,
            message=user_message,
            max_turns=10
        )
        
        if self.group_chat.messages:
            last_message = self.group_chat.messages[-1]
            if hasattr(last_message, 'content'):
                response = last_message.content
            else:
                response = str(last_message)
            logger.info(f"Response: {response}")
            return response
        else:
            return "No response generated."
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "version": AGENT_VERSION,
            "agents_count": len(self.agents),
            "agents": [agent.name for agent in self.agents],
            "status": "ready"
        }


def main():
    """Main function"""
    logger.info("=" * 60)
    logger.info("Command Agent - Starting...")
    logger.info("=" * 60)
    
    try:
        agent = CommandAgent()
        
        logger.info("\n" + "=" * 60)
        logger.info("Command Agent Ready!")
        logger.info("=" * 60)
        logger.info(f"Status: {agent.get_agent_status()}")
        logger.info("\nEnter your questions (type 'exit' to quit):\n")
        
        print("\nCommand Agent initialized. Testing with sample question...\n")
        
        test_message = "What's the current weather forecast and how does it affect our search operations?"
        print(f"Question: {test_message}\n")
        
        response = agent.chat(test_message)
        print(f"Response: {response}\n")
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
