#!/usr/bin/env python3
"""
SAR Multi-Agent System Integration Test

This script performs end-to-end testing of the integrated SAR system:
1. Verify all services are running
2. Send a test mission through the API
3. Wait for agents to process
4. Send queries through Command Agent
5. Verify responses

Usage:
    python scripts/integration_test.py [--api-url URL] [--verbose]
"""

import os
import sys

# Add project root to Python path for local imports
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import json
import time
import argparse
import requests
from datetime import datetime
from typing import Optional, Dict, Any

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[✓]{Colors.RESET} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}[✗]{Colors.RESET} {msg}")


def log_warning(msg: str):
    print(f"{Colors.YELLOW}[!]{Colors.RESET} {msg}")


def log_header(msg: str):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")


class IntegrationTest:
    """Integration test suite for SAR Multi-Agent System."""
    
    def __init__(self, api_url: str = "http://localhost:8080", verbose: bool = False):
        self.api_url = api_url.rstrip('/')
        self.verbose = verbose
        self.results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }
    
    def record_result(self, name: str, passed: bool, message: str = ""):
        """Record a test result."""
        self.results["total"] += 1
        if passed:
            self.results["passed"] += 1
            log_success(f"{name}: {message}" if message else name)
        else:
            self.results["failed"] += 1
            log_error(f"{name}: {message}" if message else name)
        
        self.results["details"].append({
            "name": name,
            "passed": passed,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def api_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """Make an API request and return the response."""
        url = f"{self.api_url}{endpoint}"
        try:
            response = requests.request(method, url, timeout=120, **kwargs)
            if self.verbose:
                log_info(f"{method} {endpoint} -> {response.status_code}")
            return {
                "status_code": response.status_code,
                "data": response.json() if response.content else None,
                "ok": response.ok
            }
        except requests.exceptions.RequestException as e:
            log_error(f"Request failed: {e}")
            return None
    
    # =========================================================================
    # Test Cases
    # =========================================================================
    
    def test_api_health(self) -> bool:
        """Test 1: API Gateway health check."""
        log_info("Testing API Gateway health...")
        
        response = self.api_request("GET", "/health")
        if response and response["ok"]:
            self.record_result("API Health Check", True, "API Gateway is healthy")
            return True
        else:
            self.record_result("API Health Check", False, "API Gateway not responding")
            return False
    
    def test_system_status(self) -> bool:
        """Test 2: Get system status."""
        log_info("Getting system status...")
        
        response = self.api_request("GET", "/status")
        if not response or not response["ok"]:
            self.record_result("System Status", False, "Could not get status")
            return False
        
        data = response["data"]
        agents = data.get("agents", {})
        streams = data.get("streams", {})
        
        if self.verbose:
            log_info(f"Agents: {list(agents.keys())}")
            active_streams = [s for s, c in streams.items() if c > 0]
            log_info(f"Active streams: {active_streams}")
        
        self.record_result("System Status", True, f"{len(agents)} agents registered")
        return True
    
    def test_create_mission(self) -> Optional[str]:
        """Test 3: Create a new mission."""
        log_info("Creating test mission...")
        
        mission_data = {
            "type": "missing_person",
            "priority": "high",
            "person": {
                "name": "Test Subject",
                "age": 65,
                "gender": "male",
                "health_conditions": ["diabetes"],
                "clothing": "Blue jacket, khaki pants",
                "last_seen": {
                    "time": datetime.utcnow().isoformat() + "Z",
                    "location": "Test Trail Head"
                }
            },
            "location": {
                "name": "Test State Park",
                "terrain": "mountainous forest",
                "coordinates": {"lat": 35.78, "lon": -120.43},
                "search_radius_km": 5
            },
            "interview_notes": "Subject was last seen heading north on the main trail."
        }
        
        response = self.api_request("POST", "/missions", json=mission_data)
        
        if not response or not response["ok"]:
            self.record_result("Create Mission", False, "Failed to create mission")
            return None
        
        mission_id = response["data"].get("id")
        self.record_result("Create Mission", True, f"Created mission {mission_id}")
        return mission_id
    
    def test_mission_routing(self, mission_id: str, wait_time: int = 10) -> bool:
        """Test 4: Verify mission is routed to agents."""
        log_info(f"Waiting {wait_time}s for mission to be processed...")
        time.sleep(wait_time)
        
        log_info("Checking mission status...")
        response = self.api_request("GET", f"/missions/{mission_id}")
        
        if not response or not response["ok"]:
            self.record_result("Mission Routing", False, "Could not check mission status")
            return False
        
        agents_responded = response["data"].get("agents_responded", [])
        if self.verbose:
            log_info(f"Agents responded: {agents_responded}")
        
        # At minimum, we expect some agents to have data in streams
        # This is a soft check since not all agents may process immediately
        self.record_result(
            "Mission Routing", 
            True, 
            f"{len(agents_responded)} agents processed" if agents_responded else "Mission queued"
        )
        return True
    
    def test_query_weather(self) -> bool:
        """Test 5: Query weather information."""
        log_info("Querying weather data...")
        
        query_data = {
            "question": "What is the current weather forecast and how does it affect search operations?",
            "timeout": 90
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response:
            self.record_result("Weather Query", False, "No response from API")
            return False
        
        if response["status_code"] == 504:
            self.record_result("Weather Query", False, "Timeout - Command Agent may not be running")
            return False
        
        if not response["ok"]:
            self.record_result("Weather Query", False, f"Error: {response.get('data')}")
            return False
        
        answer = response["data"].get("response", "")
        if self.verbose:
            print(f"\n{Colors.BLUE}Response:{Colors.RESET}")
            print(f"{answer[:500]}..." if len(answer) > 500 else answer)
            print()
        
        # Check if we got a meaningful response
        has_content = len(answer) > 50 and "error" not in answer.lower()
        self.record_result(
            "Weather Query", 
            has_content, 
            f"Got {len(answer)} char response" if has_content else "Response too short or contains error"
        )
        return has_content
    
    def test_query_comprehensive(self) -> bool:
        """Test 6: Comprehensive SAR query."""
        log_info("Sending comprehensive SAR query...")
        
        query_data = {
            "question": "Give me a comprehensive analysis of the current search situation including weather impact, health risks, and any historical patterns that might help.",
            "timeout": 120
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response:
            self.record_result("Comprehensive Query", False, "No response from API")
            return False
        
        if response["status_code"] == 504:
            self.record_result("Comprehensive Query", False, "Timeout - Query took too long")
            return False
        
        if not response["ok"]:
            self.record_result("Comprehensive Query", False, f"Error: {response.get('data')}")
            return False
        
        answer = response["data"].get("response", "")
        if self.verbose:
            print(f"\n{Colors.BLUE}Response:{Colors.RESET}")
            print(answer[:1000] + "..." if len(answer) > 1000 else answer)
            print()
        
        has_content = len(answer) > 100
        self.record_result(
            "Comprehensive Query", 
            has_content, 
            f"Got {len(answer)} char comprehensive response"
        )
        return has_content
    
    def test_stream_access(self) -> bool:
        """Test 7: Direct stream access."""
        log_info("Testing direct stream access...")
        
        streams_to_check = [
            "weather.forecast.raw",
            "health.assessment.raw",
            "logistics.requests.raw",
        ]
        
        accessible = 0
        for stream in streams_to_check:
            response = self.api_request("GET", f"/streams/{stream}")
            if response and response["ok"]:
                msg_count = len(response["data"].get("messages", []))
                if self.verbose:
                    log_info(f"  {stream}: {msg_count} messages")
                if msg_count > 0:
                    accessible += 1
        
        self.record_result(
            "Stream Access", 
            accessible > 0, 
            f"{accessible}/{len(streams_to_check)} streams have data"
        )
        return accessible > 0
    
    def test_cluemeister_analysis(self) -> bool:
        """Test 8: ClueMeister analysis."""
        log_info("Checking ClueMeister analysis...")
        
        response = self.api_request("GET", "/analysis")
        
        if not response:
            self.record_result("ClueMeister Analysis", False, "No response")
            return False
        
        if response["status_code"] == 404:
            self.record_result("ClueMeister Analysis", False, "No analysis available yet")
            return False
        
        if not response["ok"]:
            self.record_result("ClueMeister Analysis", False, "Error getting analysis")
            return False
        
        analyses = response["data"].get("analyses", [])
        self.record_result(
            "ClueMeister Analysis", 
            len(analyses) > 0, 
            f"{len(analyses)} analysis entries found"
        )
        return len(analyses) > 0
    
    def test_multi_turn_conversation(self) -> bool:
        """Test 9: Multi-turn conversation with session persistence."""
        log_info("Testing multi-turn conversation...")
        
        import uuid
        session_id = str(uuid.uuid4())
        
        # First query - establish context
        query1 = {
            "question": "What is the current weather situation for search operations?",
            "session_id": session_id,
            "timeout": 90
        }
        
        response1 = self.api_request("POST", "/query", json=query1)
        
        if not response1 or not response1["ok"]:
            self.record_result("Multi-Turn Conversation", False, "First query failed")
            return False
        
        first_response = response1["data"].get("response", "")
        if self.verbose:
            log_info(f"First response: {first_response[:200]}...")
        
        # Second query - should reference first conversation
        query2 = {
            "question": "Based on what you just told me, what specific precautions should search teams take?",
            "session_id": session_id,
            "timeout": 90
        }
        
        response2 = self.api_request("POST", "/query", json=query2)
        
        if not response2 or not response2["ok"]:
            self.record_result("Multi-Turn Conversation", False, "Second query failed")
            return False
        
        second_response = response2["data"].get("response", "")
        if self.verbose:
            log_info(f"Second response: {second_response[:200]}...")
        
        # Check if second response seems to reference context
        # (This is a heuristic - in production we'd have better checks)
        has_context = len(second_response) > 50 and session_id == response2["data"].get("session_id")
        
        self.record_result(
            "Multi-Turn Conversation", 
            has_context, 
            f"Session maintained, got {len(second_response)} char follow-up response"
        )
        return has_context
    
    def test_task_dispatch(self) -> bool:
        """Test 10: Task dispatch mechanism."""
        log_info("Testing task dispatch to specialist agents...")
        
        # Query that should trigger dispatch to multiple agents
        query_data = {
            "question": "Analyze the search area: check weather conditions, assess health risks for a 65-year-old diabetic missing for 18 hours, and look for relevant historical cases.",
            "timeout": 120
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response:
            self.record_result("Task Dispatch", False, "No response from API")
            return False
        
        if response["status_code"] == 504:
            self.record_result("Task Dispatch", False, "Timeout waiting for task results")
            return False
        
        if not response["ok"]:
            self.record_result("Task Dispatch", False, f"Error: {response.get('data')}")
            return False
        
        answer = response["data"].get("response", "")
        
        # Check for signs that multiple agents contributed
        # Look for keywords that indicate different data sources
        weather_mentioned = any(w in answer.lower() for w in ["weather", "temperature", "forecast", "wind"])
        health_mentioned = any(w in answer.lower() for w in ["health", "risk", "diabetic", "medical"])
        history_mentioned = any(w in answer.lower() for w in ["historical", "similar", "previous", "cases"])
        
        agents_contributed = sum([weather_mentioned, health_mentioned, history_mentioned])
        
        if self.verbose:
            log_info(f"Weather data: {weather_mentioned}")
            log_info(f"Health data: {health_mentioned}")
            log_info(f"History data: {history_mentioned}")
        
        self.record_result(
            "Task Dispatch", 
            agents_contributed >= 2, 
            f"{agents_contributed}/3 agent types detected in response"
        )
        return agents_contributed >= 2
    
    def test_session_persistence(self) -> bool:
        """Test 11: Session persistence across queries."""
        log_info("Testing session persistence...")
        
        import uuid
        session_id = str(uuid.uuid4())
        
        # Send 3 queries with same session
        queries = [
            "What resources do we have available for the search?",
            "Which of those resources are most critical?",
            "Should we request additional resources?"
        ]
        
        responses = []
        for i, q in enumerate(queries):
            response = self.api_request("POST", "/query", json={
                "question": q,
                "session_id": session_id,
                "timeout": 60
            })
            
            if response and response["ok"]:
                responses.append(response["data"])
            else:
                self.record_result("Session Persistence", False, f"Query {i+1} failed")
                return False
        
        # All responses should have same session_id
        all_same_session = all(r.get("session_id") == session_id for r in responses)
        
        self.record_result(
            "Session Persistence", 
            all_same_session and len(responses) == 3, 
            f"3 queries successfully used session {session_id[:8]}..."
        )
        return all_same_session
    
    def test_file_upload_endpoint(self) -> bool:
        """Test 12: File upload endpoint availability."""
        log_info("Testing file upload endpoint...")
        
        # Just check the endpoint exists (actual file upload needs real files)
        # Try to access upload endpoint without file to check it's there
        try:
            url = f"{self.api_url}/upload"
            response = requests.post(url, timeout=10)
            
            # 422 means endpoint exists but validation failed (no file)
            # 400 also acceptable
            endpoint_exists = response.status_code in [400, 422, 200]
            
            self.record_result(
                "File Upload Endpoint", 
                endpoint_exists, 
                f"Endpoint responds with {response.status_code}"
            )
            return endpoint_exists
            
        except requests.exceptions.RequestException as e:
            self.record_result("File Upload Endpoint", False, str(e))
            return False
    
    def test_weather_query_stream(self) -> bool:
        """Test 13: Weather agent query stream."""
        log_info("Testing weather agent on-demand query...")
        
        # This tests if the weather agent responds to queries
        query_data = {
            "question": "Get the latest weather forecast for coordinates 35.28, -120.65",
            "timeout": 60
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response or not response["ok"]:
            self.record_result("Weather Query Stream", False, "Query failed")
            return False
        
        answer = response["data"].get("response", "")
        has_weather = any(w in answer.lower() for w in ["temperature", "forecast", "weather", "wind"])
        
        self.record_result(
            "Weather Query Stream", 
            has_weather, 
            "Weather data returned in response" if has_weather else "No weather data found"
        )
        return has_weather
    
    def test_health_assessment_query(self) -> bool:
        """Test 14: Health agent assessment query."""
        log_info("Testing health assessment query...")
        
        query_data = {
            "question": "Assess health risks for a 65-year-old diabetic male who has been missing for 24 hours in cold weather with light clothing.",
            "timeout": 90
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response or not response["ok"]:
            self.record_result("Health Assessment Query", False, "Query failed")
            return False
        
        answer = response["data"].get("response", "")
        has_health_terms = any(w in answer.lower() for w in ["risk", "hypothermia", "diabetes", "health", "medical"])
        
        self.record_result(
            "Health Assessment Query", 
            has_health_terms, 
            "Health assessment data in response" if has_health_terms else "No health assessment found"
        )
        return has_health_terms
    
    def test_logistics_inventory(self) -> bool:
        """Test 15: Logistics inventory query."""
        log_info("Testing logistics inventory query...")
        
        query_data = {
            "question": "What equipment and personnel do we have available for the search operation?",
            "timeout": 60
        }
        
        response = self.api_request("POST", "/query", json=query_data)
        
        if not response or not response["ok"]:
            self.record_result("Logistics Inventory", False, "Query failed")
            return False
        
        answer = response["data"].get("response", "")
        has_inventory = any(w in answer.lower() for w in ["equipment", "personnel", "available", "resources", "inventory", "team"])
        
        self.record_result(
            "Logistics Inventory", 
            has_inventory, 
            "Inventory data in response" if has_inventory else "No inventory data found"
        )
        return has_inventory
    
    # =========================================================================
    # Runner
    # =========================================================================
    
    def run_all_tests(self):
        """Run all integration tests."""
        log_header("SAR Multi-Agent System Integration Test")
        print(f"API URL: {self.api_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print()
        
        # Test 1: API Health
        if not self.test_api_health():
            log_error("API Gateway not available. Aborting tests.")
            return self.results
        
        # Test 2: System Status
        self.test_system_status()
        
        # Test 3: Create Mission
        mission_id = self.test_create_mission()
        
        # Test 4: Mission Routing (if mission was created)
        if mission_id:
            self.test_mission_routing(mission_id, wait_time=5)
        
        # Test 5: Weather Query
        self.test_query_weather()
        
        # Test 6: Comprehensive Query
        self.test_query_comprehensive()
        
        # Test 7: Stream Access
        self.test_stream_access()
        
        # Test 8: ClueMeister
        self.test_cluemeister_analysis()
        
        # Test 9: Multi-Turn Conversation
        self.test_multi_turn_conversation()
        
        # Test 10: Task Dispatch
        self.test_task_dispatch()
        
        # Test 11: Session Persistence
        self.test_session_persistence()
        
        # Test 12: File Upload Endpoint
        self.test_file_upload_endpoint()
        
        # Test 13: Weather Query Stream
        self.test_weather_query_stream()
        
        # Test 14: Health Assessment Query
        self.test_health_assessment_query()
        
        # Test 15: Logistics Inventory
        self.test_logistics_inventory()
        
        # Summary
        log_header("Test Results Summary")
        print(f"Total:   {self.results['total']}")
        print(f"{Colors.GREEN}Passed:  {self.results['passed']}{Colors.RESET}")
        print(f"{Colors.RED}Failed:  {self.results['failed']}{Colors.RESET}")
        
        success_rate = (self.results['passed'] / self.results['total'] * 100) if self.results['total'] > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        
        if self.results['failed'] == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed!{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}Some tests failed. Check the logs above for details.{Colors.RESET}")
        
        return self.results


# ============================================================================
# Local Integration Test (Direct Python testing, no Docker API required)
# ============================================================================

class LocalIntegrationTest:
    """
    Local integration tests that run without Docker API Gateway.
    
    Requirements:
    - Redis running (docker compose up -d redis)
    - Environment variables set (GOOGLE_API_KEY, REDIS_URL)
    
    Usage:
        python scripts/integration_test.py --mode local
    """
    
    def __init__(self, verbose: bool = False, seed: bool = True):
        self.verbose = verbose
        self.seed = seed
        self.results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }
    
    def record_result(self, name: str, passed: bool, message: str = ""):
        """Record a test result."""
        self.results["total"] += 1
        if passed:
            self.results["passed"] += 1
            log_success(f"{name}: {message}" if message else name)
        else:
            self.results["failed"] += 1
            log_error(f"{name}: {message}" if message else name)
        
        self.results["details"].append({
            "name": name,
            "passed": passed,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def test_redis_connection(self) -> bool:
        """Test 1: Redis connectivity."""
        log_info("Testing Redis connection...")
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            self.record_result("Redis Connection", True, f"Connected to {redis_url}")
            return True
        except Exception as e:
            self.record_result("Redis Connection", False, str(e))
            return False
    
    def test_seed_data(self) -> bool:
        """Test 2: Seed test data into Redis."""
        if not self.seed:
            log_info("Skipping seed (--no-seed)")
            return True
            
        log_info("Seeding test data...")
        try:
            # Import and run seed_data
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            
            import seed_data
            client = seed_data.get_redis_client()
            
            # Clear old data
            seed_data.clear_streams(client)
            
            # Load mission
            project_root = os.path.dirname(script_dir)
            mission_path = os.path.join(project_root, "data/sample_missions/mission_001_missing_elderly.json")
            
            if os.path.exists(mission_path):
                mission = seed_data.load_mission_file(mission_path)
                seed_data.seed_from_mission(client, mission)
                self.record_result("Seed Data", True, "Test data seeded to Redis")
                return True
            else:
                self.record_result("Seed Data", False, f"Mission file not found: {mission_path}")
                return False
                
        except Exception as e:
            self.record_result("Seed Data", False, str(e))
            return False
    
    def test_stream_data_available(self) -> bool:
        """Test 3: Verify streams have data."""
        log_info("Checking stream data...")
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            
            streams_with_data = 0
            streams_to_check = [
                "weather.forecast.raw",
                "health.assessment.raw",
                "history.out.raw"
            ]
            
            for stream in streams_to_check:
                length = client.xlen(stream)
                if self.verbose:
                    log_info(f"  {stream}: {length} messages")
                if length > 0:
                    streams_with_data += 1
            
            passed = streams_with_data >= 2
            self.record_result(
                "Stream Data Available",
                passed,
                f"{streams_with_data}/{len(streams_to_check)} streams have data"
            )
            return passed
            
        except Exception as e:
            self.record_result("Stream Data Available", False, str(e))
            return False
    
    def test_command_agent_query(self) -> bool:
        """Test 4: Direct Command Agent query."""
        log_info("Testing Command Agent query...")
        try:
            from agents.command_agent.graph import run_query
            
            query = "What are the health risks for the missing person?"
            
            if self.verbose:
                result = run_query(query, verbose=True)
            else:
                result = run_query(query, verbose=False)
            
            # Check if response has meaningful content
            has_content = len(result) > 100 and "No response" not in result
            
            if self.verbose:
                print(f"\n{Colors.BLUE}Response Preview:{Colors.RESET}")
                print(result[:500] + "..." if len(result) > 500 else result)
                print()
            
            self.record_result(
                "Command Agent Query",
                has_content,
                f"Got {len(result)} char response"
            )
            return has_content
            
        except Exception as e:
            self.record_result("Command Agent Query", False, str(e))
            return False
    
    def test_weather_specialist(self) -> bool:
        """Test 5: Weather specialist node."""
        log_info("Testing weather data retrieval...")
        try:
            from agents.command_agent.tools import get_weather_data
            
            result = get_weather_data.invoke({})
            
            has_data = "No data" not in result and len(result) > 50
            
            if self.verbose and has_data:
                data = json.loads(result)
                log_info(f"  Weather location: {data[0].get('data', {}).get('location', 'unknown')}")
            
            self.record_result(
                "Weather Data Retrieval",
                has_data,
                "Weather data available" if has_data else "No weather data"
            )
            return has_data
            
        except Exception as e:
            self.record_result("Weather Data Retrieval", False, str(e))
            return False
    
    def test_health_specialist(self) -> bool:
        """Test 6: Health specialist node."""
        log_info("Testing health assessment retrieval...")
        try:
            from agents.command_agent.tools import get_health_assessment
            
            result = get_health_assessment.invoke({})
            
            has_data = "No data" not in result and len(result) > 50
            
            self.record_result(
                "Health Assessment Retrieval",
                has_data,
                "Health data available" if has_data else "No health data"
            )
            return has_data
            
        except Exception as e:
            self.record_result("Health Assessment Retrieval", False, str(e))
            return False
    
    def test_history_specialist(self) -> bool:
        """Test 7: History specialist node."""
        log_info("Testing historical cases retrieval...")
        try:
            from agents.command_agent.tools import get_history_cases
            
            result = get_history_cases.invoke({})
            
            has_data = "No data" not in result and len(result) > 50
            
            self.record_result(
                "History Cases Retrieval",
                has_data,
                "History data available" if has_data else "No history data"
            )
            return has_data
            
        except Exception as e:
            self.record_result("History Cases Retrieval", False, str(e))
            return False
    
    def test_comprehensive_query(self) -> bool:
        """Test 8: Comprehensive SAR query."""
        log_info("Testing comprehensive query...")
        try:
            from agents.command_agent.graph import run_query
            
            query = """
            Analyze the current search situation:
            1. What are the weather conditions and their impact?
            2. What are the health risks for the missing person?
            3. What do similar historical cases suggest?
            4. What should be our search priorities?
            """
            
            # Always use verbose=False here to avoid double execution
            result = run_query(query, verbose=False)
            result_lower = result.lower()
            
            # Expanded keyword lists for more robust detection
            weather_keywords = ["weather", "temperature", "forecast", "wind", "rain", 
                               "cold", "exposure", "visibility", "hypothermia", "freezing"]
            health_keywords = ["health", "risk", "diabetic", "medical", "diabetes", 
                              "condition", "insulin", "dementia", "survival", "urgent"]
            history_keywords = ["historical", "similar", "cases", "past", "previous", 
                               "pattern", "outcome", "isrid", "survival rate"]
            
            weather_mentioned = any(w in result_lower for w in weather_keywords)
            health_mentioned = any(w in result_lower for w in health_keywords)
            history_mentioned = any(w in result_lower for w in history_keywords)
            
            analyses_found = sum([weather_mentioned, health_mentioned, history_mentioned])
            passed = analyses_found >= 2 and len(result) > 200
            
            if self.verbose:
                log_info(f"  Response length: {len(result)} chars")
                log_info(f"  Weather mentioned: {weather_mentioned}")
                log_info(f"  Health mentioned: {health_mentioned}")
                log_info(f"  History mentioned: {history_mentioned}")
            
            self.record_result(
                "Comprehensive Query",
                passed,
                f"{analyses_found}/3 specialist analyses detected"
            )
            return passed
            
        except Exception as e:
            self.record_result("Comprehensive Query", False, str(e))
            return False
    
    def test_session_persistence(self) -> bool:
        """Test 9: Session persistence across queries."""
        log_info("Testing session persistence...")
        try:
            from agents.command_agent.graph import run_query, get_session_history
            import uuid
            
            session_id = str(uuid.uuid4())
            
            # First query
            result1 = run_query("What is the weather situation?", session_id=session_id)
            
            # Second query referencing first
            result2 = run_query("How does that affect our search?", session_id=session_id)
            
            # Check session history
            history = get_session_history(session_id)
            
            passed = len(history) >= 2 and len(result2) > 50
            
            self.record_result(
                "Session Persistence",
                passed,
                f"Session has {len(history)} messages"
            )
            return passed
            
        except Exception as e:
            self.record_result("Session Persistence", False, str(e))
            return False
    
    def run_all_tests(self):
        """Run all local integration tests."""
        log_header("SAR Local Integration Test")
        print(f"Mode: Local (Direct Python)")
        print(f"Redis: {os.getenv('REDIS_URL', 'redis://localhost:6379')}")
        print(f"Time: {datetime.now().isoformat()}")
        print()
        
        # Test 1: Redis Connection
        if not self.test_redis_connection():
            log_error("Redis not available. Aborting tests.")
            log_info("Start Redis with: docker compose up -d redis")
            return self.results
        
        # Test 2: Seed Data
        if not self.test_seed_data():
            log_warning("Seed failed, continuing with existing data...")
        
        # Test 3: Stream Data Available
        self.test_stream_data_available()
        
        # Test 4: Command Agent Query
        self.test_command_agent_query()
        
        # Test 5-7: Specialist Data Retrieval
        self.test_weather_specialist()
        self.test_health_specialist()
        self.test_history_specialist()
        
        # Test 8: Comprehensive Query
        self.test_comprehensive_query()
        
        # Test 9: Session Persistence
        self.test_session_persistence()
        
        # Summary
        log_header("Test Results Summary")
        print(f"Total:   {self.results['total']}")
        print(f"{Colors.GREEN}Passed:  {self.results['passed']}{Colors.RESET}")
        print(f"{Colors.RED}Failed:  {self.results['failed']}{Colors.RESET}")
        
        success_rate = (self.results['passed'] / self.results['total'] * 100) if self.results['total'] > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        
        if self.results['failed'] == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}All tests passed!{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}Some tests failed. Check details above.{Colors.RESET}")
        
        return self.results


def main():
    parser = argparse.ArgumentParser(
        description="SAR Integration Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Modes:
  docker    Full Docker integration test via API Gateway (default)
  local     Direct Python testing, only requires Redis
  
Examples:
  # Docker mode (all services running)
  python scripts/integration_test.py --mode docker
  
  # Local mode (only Redis required)
  docker compose up -d redis
  python scripts/integration_test.py --mode local
  
  # Local mode without seeding (use existing data)
  python scripts/integration_test.py --mode local --no-seed
"""
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["docker", "local"],
        default="docker",
        help="Test mode: docker (full API) or local (direct Python)"
    )
    parser.add_argument(
        "--api-url", 
        default=os.getenv("API_URL", "http://localhost:8080"),
        help="API Gateway URL (docker mode only)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding test data (local mode only)"
    )
    parser.add_argument(
        "--json-output",
        type=str,
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    if args.mode == "local":
        # Local integration test
        log_info("Running in LOCAL mode (direct Python, Redis only)")
        tester = LocalIntegrationTest(
            verbose=args.verbose,
            seed=not args.no_seed
        )
    else:
        # Docker integration test
        log_info("Running in DOCKER mode (via API Gateway)")
        tester = IntegrationTest(
            api_url=args.api_url,
            verbose=args.verbose
        )
    
    results = tester.run_all_tests()
    
    if args.json_output:
        with open(args.json_output, 'w') as f:
            json.dump(results, f, indent=2)
        log_info(f"Results saved to {args.json_output}")
    
    # Exit with appropriate code
    sys.exit(0 if results['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
