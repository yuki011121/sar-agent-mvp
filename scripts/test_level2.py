#!/usr/bin/env python3
"""
Level 2 Integration Tests: Single Agent Dynamic Input Testing

Tests individual agents' ability to receive dynamic inputs via query streams
and respond with properly correlated outputs.

Usage:
    python scripts/test_level2.py --agent weather --timeout 30
    python scripts/test_level2.py --agent weather --coords "37.7749,-122.4194"
    python scripts/test_level2.py --all
"""

import argparse
import json
import logging
import os
import sys
import subprocess
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

# Add project root to path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

import redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("level2-test")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


def create_envelope(payload: Dict[str, Any], source: str = "test-harness") -> Dict[str, str]:
    """Create MCP A2A envelope for publishing."""
    from shared import wrap_envelope
    msg = wrap_envelope(
        payload=payload,
        source_name=source,
        source_version="1.0",
        target_stream="test"
    )
    return {"body": msg.model_dump_json()}


def test_weather_dynamic_coords(
    lat: float = 37.7749, 
    lon: float = -122.4194,
    timeout: int = 30
) -> Tuple[bool, str]:
    """
    Test Weather Agent with dynamic coordinates.
    
    Args:
        lat: Latitude (default: San Francisco)
        lon: Longitude (default: San Francisco)
        timeout: Max seconds to wait for response
        
    Returns:
        (success, message) tuple
    """
    logger.info(f"Testing Weather Agent with coords: ({lat}, {lon})")
    
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    task_id = f"test-weather-{uuid.uuid4().hex[:8]}"
    
    # Clear old test data
    r.delete("weather.forecast.raw")
    
    # Publish query
    query_payload = {
        "task_id": task_id,
        "lat": lat,
        "lon": lon,
        "requested_at": datetime.now().isoformat()
    }
    
    envelope_data = create_envelope(query_payload, source="level2-test")
    r.xadd("weather.query.raw", envelope_data)
    logger.info(f"Published weather query with task_id: {task_id}")
    
    # Wait for response with matching task_id
    start = time.time()
    while time.time() - start < timeout:
        entries = r.xrevrange("weather.forecast.raw", count=10)
        for entry_id, data in entries:
            body = data.get("body", "{}")
            try:
                msg = json.loads(body)
                msg_payload = msg.get("payload", {})
                if msg_payload.get("task_id") == task_id:
                    location = msg_payload.get("location", {})
                    forecasts = msg_payload.get("forecasts", [])
                    
                    # Verify location matches
                    resp_lat = location.get("latitude")
                    resp_lon = location.get("longitude")
                    
                    if resp_lat == lat and resp_lon == lon and len(forecasts) > 0:
                        return True, f"Received {len(forecasts)} forecast periods for ({lat}, {lon})"
                    else:
                        return False, f"Location mismatch or empty forecasts: got ({resp_lat}, {resp_lon})"
            except json.JSONDecodeError:
                continue
        time.sleep(1)
    
    return False, f"Timeout waiting for response (task_id: {task_id})"


def test_weather_default_coords(timeout: int = 30) -> Tuple[bool, str]:
    """Test Weather Agent with default coordinates (no lat/lon specified)."""
    logger.info("Testing Weather Agent with default coords")
    
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    task_id = f"test-weather-default-{uuid.uuid4().hex[:8]}"
    
    # Publish query without coords
    query_payload = {
        "task_id": task_id,
        "requested_at": datetime.now().isoformat()
    }
    
    envelope_data = create_envelope(query_payload, source="level2-test")
    r.xadd("weather.query.raw", envelope_data)
    logger.info(f"Published weather query (default coords) with task_id: {task_id}")
    
    # Wait for response
    start = time.time()
    while time.time() - start < timeout:
        entries = r.xrevrange("weather.forecast.raw", count=10)
        for entry_id, data in entries:
            body = data.get("body", "{}")
            try:
                msg = json.loads(body)
                msg_payload = msg.get("payload", {})
                if msg_payload.get("task_id") == task_id:
                    forecasts = msg_payload.get("forecasts", [])
                    if len(forecasts) > 0:
                        return True, f"Received {len(forecasts)} forecast periods (default coords)"
                    else:
                        return False, "Empty forecasts returned"
            except json.JSONDecodeError:
                continue
        time.sleep(1)
    
    return False, f"Timeout waiting for response (task_id: {task_id})"


def start_agent_background(agent_name: str) -> subprocess.Popen:
    """Start an agent in background and return the process."""
    cmd = [sys.executable, "-m", f"agents.{agent_name}.main"]
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
    logger.info(f"Started {agent_name} agent (PID: {proc.pid})")
    time.sleep(3)  # Give agent time to initialize
    return proc


def run_weather_tests(coords: Optional[str] = None, timeout: int = 30, start_agent: bool = True):
    """Run all Weather Agent tests."""
    agent_proc = None
    results = []
    
    try:
        if start_agent:
            logger.info("Starting Weather Agent...")
            agent_proc = start_agent_background("weather")
        
        # Test 1: Custom coordinates
        if coords:
            lat, lon = map(float, coords.split(","))
        else:
            lat, lon = 34.0522, -118.2437  # Los Angeles
            
        success, msg = test_weather_dynamic_coords(lat, lon, timeout)
        results.append(("Dynamic Coordinates", success, msg))
        logger.info(f"[{'✓' if success else '✗'}] Dynamic Coordinates: {msg}")
        
        # Test 2: Default coordinates
        success, msg = test_weather_default_coords(timeout)
        results.append(("Default Coordinates", success, msg))
        logger.info(f"[{'✓' if success else '✗'}] Default Coordinates: {msg}")
        
    finally:
        if agent_proc:
            logger.info("Stopping Weather Agent...")
            agent_proc.terminate()
            agent_proc.wait(timeout=5)
    
    return results


def test_health_dynamic_person(
    person_info: Optional[Dict[str, Any]] = None,
    timeout: int = 45
) -> Tuple[bool, str]:
    """
    Test Health Agent with custom person info.
    
    Args:
        person_info: Person data dict (default: test person with medical conditions)
        timeout: Max seconds to wait for response
        
    Returns:
        (success, message) tuple
    """
    if person_info is None:
        person_info = {
            "name": "John Smith",
            "age": 72,
            "weight_kg": 68,
            "medical_conditions": ["type 2 diabetes", "high blood pressure"],
            "medications": ["metformin", "lisinopril"],
            "mobility": "limited - uses walking stick",
            "last_seen_wearing": "blue jacket, khaki pants",
            "time_missing_hours": 18
        }
    
    logger.info(f"Testing Health Agent with person: {person_info.get('name', 'Unknown')}")
    
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    task_id = f"test-health-{uuid.uuid4().hex[:8]}"
    
    # Publish query
    query_payload = {
        "task_id": task_id,
        "person_info": person_info,
        "requested_at": datetime.now().isoformat()
    }
    
    envelope_data = create_envelope(query_payload, source="level2-test")
    r.xadd("health.assess.raw", envelope_data)
    logger.info(f"Published health query with task_id: {task_id}")
    
    # Wait for response with matching task_id
    start = time.time()
    while time.time() - start < timeout:
        entries = r.xrevrange("health.assessment.raw", count=10)
        for entry_id, data in entries:
            body = data.get("body", "{}")
            try:
                msg = json.loads(body)
                msg_payload = msg.get("payload", {})
                if msg_payload.get("task_id") == task_id:
                    # Check for expected response fields
                    # risk_level may be in assessment dict or at top level
                    assessment = msg_payload.get("assessment", {})
                    risk_level = (
                        msg_payload.get("risk_level") or 
                        assessment.get("risk_level") if isinstance(assessment, dict) else None
                    )
                    
                    if risk_level:
                        return True, f"Risk level: {risk_level}, assessment received"
                    else:
                        return False, "Response missing risk_level field"
            except json.JSONDecodeError:
                continue
        time.sleep(1)
    
    return False, f"Timeout waiting for response (task_id: {task_id})"


def run_health_tests(timeout: int = 45, start_agent: bool = True):
    """Run all Health Agent tests."""
    agent_proc = None
    results = []
    
    try:
        if start_agent:
            logger.info("Starting Health Agent...")
            agent_proc = start_agent_background("health")
        
        # Test 1: Default test person (elderly with diabetes)
        success, msg = test_health_dynamic_person(timeout=timeout)
        results.append(("Dynamic Person Assessment", success, msg))
        logger.info(f"[{'✓' if success else '✗'}] Dynamic Person Assessment: {msg}")
        
        # Test 2: Different person profile (child)
        child_info = {
            "name": "Emma Wilson",
            "age": 8,
            "weight_kg": 25,
            "medical_conditions": ["asthma"],
            "medications": ["inhaler (as needed)"],
            "mobility": "normal",
            "experience_level": "novice hiker",
            "time_missing_hours": 6
        }
        success, msg = test_health_dynamic_person(person_info=child_info, timeout=timeout)
        results.append(("Child Profile Assessment", success, msg))
        logger.info(f"[{'✓' if success else '✗'}] Child Profile Assessment: {msg}")
        
    finally:
        if agent_proc:
            logger.info("Stopping Health Agent...")
            agent_proc.terminate()
            agent_proc.wait(timeout=5)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Level 2 Integration Tests")
    parser.add_argument("--agent", choices=["weather", "health", "photo", "interview"],
                       default="weather", help="Agent to test")
    parser.add_argument("--coords", type=str, help="Coordinates as 'lat,lon' (e.g., '37.7749,-122.4194')")
    parser.add_argument("--timeout", type=int, default=45, help="Timeout in seconds")
    parser.add_argument("--no-start", action="store_true", help="Don't start agent (assume already running)")
    parser.add_argument("--all", action="store_true", help="Run all agent tests")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("Level 2 Integration Tests: Single Agent Dynamic Input")
    print("=" * 60 + "\n")
    
    all_results = []
    
    if args.all or args.agent == "weather":
        print("Weather Agent Tests")
        print("-" * 40)
        results = run_weather_tests(
            coords=args.coords,
            timeout=args.timeout,
            start_agent=not args.no_start
        )
        all_results.extend(results)
        print()
    
    if args.all or args.agent == "health":
        print("Health Agent Tests")
        print("-" * 40)
        results = run_health_tests(
            timeout=args.timeout,
            start_agent=not args.no_start
        )
        all_results.extend(results)
        print()
    
    # Summary
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    passed = sum(1 for _, s, _ in all_results if s)
    total = len(all_results)
    
    for name, success, msg in all_results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name} - {msg}")
    
    print(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")
    print(f"Success Rate: {100 * passed / total:.1f}%\n")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
