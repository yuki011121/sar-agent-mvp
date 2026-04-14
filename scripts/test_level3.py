#!/usr/bin/env python3
"""
Level 3 Integration Tests: API Endpoint Testing

Tests the API Gateway endpoints with Command Agent in service mode.

Requirements:
- Redis running
- Seed data populated
- API Gateway and Command Agent processes started by this script

Usage:
    python scripts/test_level3.py --timeout 90
    python scripts/test_level3.py --no-seed  # Skip seeding data
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("level3-test")

API_HOST = os.getenv("API_HOST", "localhost")
API_PORT = int(os.getenv("API_PORT", "8080"))
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"


def start_service_background(service_name: str, args: List[str] = None) -> subprocess.Popen:
    """Start a service in background and return the process."""
    if service_name == "api_gateway":
        cmd = [sys.executable, "-m", "agents.api_gateway.main"]
    elif service_name == "command_agent_service":
        cmd = [sys.executable, "-m", "agents.command_agent.main", "--mode", "service"]
    else:
        cmd = [sys.executable, "-m", f"agents.{service_name}.main"]
    
    if args:
        cmd.extend(args)
    
    env = os.environ.copy()
    env["PYTHONPATH"] = _project_root
    env["UPDATE_INTERVAL_SECONDS"] = "3600"  # Don't auto-publish
    
    proc = subprocess.Popen(
        cmd,
        cwd=_project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    logger.info(f"Started {service_name} (PID: {proc.pid})")
    return proc


def wait_for_api(timeout: int = 30) -> bool:
    """Wait for API to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{API_BASE_URL}/health", timeout=2)
            if resp.status_code == 200:
                logger.info("API Gateway is ready")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            logger.warning(f"API check error: {e}")
        time.sleep(1)
    return False


def test_health_endpoint() -> Tuple[bool, str]:
    """Test /health endpoint."""
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            return True, "Health check passed"
        return False, f"Status code: {resp.status_code}"
    except Exception as e:
        return False, str(e)


def test_status_endpoint() -> Tuple[bool, str]:
    """Test /status endpoint."""
    try:
        resp = requests.get(f"{API_BASE_URL}/status", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # Check for expected fields
            if "streams" in data or "status" in data:
                return True, f"System status retrieved"
            return False, "Missing expected fields in response"
        return False, f"Status code: {resp.status_code}"
    except Exception as e:
        return False, str(e)


def test_streams_endpoint() -> Tuple[bool, str]:
    """Test /streams/{name} endpoint."""
    try:
        resp = requests.get(f"{API_BASE_URL}/streams/weather.forecast.raw", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return True, f"Retrieved {len(data)} entries from weather stream"
            elif isinstance(data, dict) and "data" in data:
                entries = data["data"]
                return True, f"Retrieved {len(entries)} entries from weather stream"
            return True, "Stream endpoint working (no data)"
        return False, f"Status code: {resp.status_code}"
    except Exception as e:
        return False, str(e)


def test_query_endpoint(timeout: int = 90) -> Tuple[bool, str]:
    """Test /query endpoint with Command Agent."""
    try:
        payload = {
            "question": "What is the current weather situation for the search area?",
            "timeout": timeout
        }
        resp = requests.post(
            f"{API_BASE_URL}/query",
            json=payload,
            timeout=timeout + 10
        )
        if resp.status_code == 200:
            data = resp.json()
            response_text = data.get("response", "")
            if len(response_text) > 100:
                # Check for weather-related content
                keywords = ["weather", "temperature", "forecast", "wind", "search"]
                found = sum(1 for k in keywords if k in response_text.lower())
                return True, f"Query response: {len(response_text)} chars, {found} keywords"
            return False, f"Response too short: {len(response_text)} chars"
        elif resp.status_code == 504:
            return False, "Timeout - Command Agent may not be responding"
        return False, f"Status code: {resp.status_code}, {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as e:
        return False, str(e)


def test_session_continuity(timeout: int = 90) -> Tuple[bool, str]:
    """Test session persistence across queries."""
    try:
        session_id = str(uuid.uuid4())
        
        # First query
        payload1 = {
            "question": "What is the weather situation?",
            "session_id": session_id,
            "timeout": timeout
        }
        resp1 = requests.post(f"{API_BASE_URL}/query", json=payload1, timeout=timeout + 10)
        if resp1.status_code != 200:
            return False, f"First query failed: {resp1.status_code}"
        
        # Follow-up query referencing previous
        payload2 = {
            "question": "How does that affect search operations?",
            "session_id": session_id,
            "timeout": timeout
        }
        resp2 = requests.post(f"{API_BASE_URL}/query", json=payload2, timeout=timeout + 10)
        if resp2.status_code != 200:
            return False, f"Follow-up query failed: {resp2.status_code}"
        
        data2 = resp2.json()
        response2 = data2.get("response", "")
        
        # Check if response has context from previous (weather)
        weather_keywords = ["weather", "temperature", "search", "conditions", "operations"]
        found = sum(1 for k in weather_keywords if k in response2.lower())
        
        if found >= 2 and len(response2) > 100:
            return True, f"Session maintained, context preserved ({found} keywords)"
        return False, f"Response may lack context: {found} keywords, {len(response2)} chars"
        
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as e:
        return False, str(e)


def run_all_tests(timeout: int = 90, start_services: bool = True, seed_data: bool = True) -> List[Tuple[str, bool, str]]:
    """Run all Level 3 tests."""
    results = []
    processes = []
    
    try:
        # Seed data if requested
        if seed_data:
            logger.info("Seeding test data...")
            subprocess.run(
                [sys.executable, "scripts/seed_data.py", "--clear"],
                cwd=_project_root,
                capture_output=True,
                timeout=60
            )
        
        if start_services:
            # Start Command Agent in service mode
            logger.info("Starting Command Agent (service mode)...")
            cmd_proc = start_service_background("command_agent_service")
            processes.append(cmd_proc)
            time.sleep(3)
            
            # Start API Gateway
            logger.info("Starting API Gateway...")
            api_proc = start_service_background("api_gateway")
            processes.append(api_proc)
        
        # Wait for API to be ready
        logger.info("Waiting for API Gateway to be ready...")
        if not wait_for_api(timeout=30):
            return [("API Startup", False, "API Gateway failed to start")]
        
        # Run tests
        tests = [
            ("Health Endpoint", test_health_endpoint),
            ("Status Endpoint", test_status_endpoint),
            ("Streams Endpoint", test_streams_endpoint),
            ("Query Endpoint", lambda: test_query_endpoint(timeout)),
            ("Session Continuity", lambda: test_session_continuity(timeout)),
        ]
        
        for name, test_fn in tests:
            logger.info(f"Running test: {name}")
            success, msg = test_fn()
            results.append((name, success, msg))
            logger.info(f"[{'✓' if success else '✗'}] {name}: {msg}")
        
    finally:
        if start_services:
            logger.info("Stopping services...")
            for proc in processes:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except:
                    proc.kill()
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Level 3 Integration Tests")
    parser.add_argument("--timeout", type=int, default=90, help="Query timeout in seconds")
    parser.add_argument("--no-start", action="store_true", help="Don't start services (assume already running)")
    parser.add_argument("--no-seed", action="store_true", help="Don't seed data")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("Level 3 Integration Tests: API Endpoints")
    print("=" * 60 + "\n")
    
    results = run_all_tests(
        timeout=args.timeout,
        start_services=not args.no_start,
        seed_data=not args.no_seed
    )
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, s, _ in results if s)
    total = len(results)
    
    for name, success, msg in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name} - {msg}")
    
    print(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")
    if total > 0:
        print(f"Success Rate: {100 * passed / total:.1f}%\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
