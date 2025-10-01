#!/usr/bin/env python3
"""
test_single_agent.py

Migrate the functionality of the original test_single_agent.sh to Python:
Usage:
  ./test_single_agent.py [command]

Commands:
  setup, cleanup, weather, health, photo-analysis, interview, logistics,
  path-analysis, redis, list, help, test-all

New Features:
  - Improved error handling and logging
  - Test result statistics and reporting
  - Support for batch testing all agents
  - Better environment checks and dependency validation
"""

import argparse
import os
import sys
import subprocess
import shlex
import time
import json
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

AVAILABLE_AGENTS = [
    "weather",
    "health",
    "photo-analysis",
    "interview",
    "logistics",
    "path-analysis",
]

# Test result statistics
class TestResults:
    def __init__(self):
        self.results: Dict[str, Dict] = {}
        self.start_time = datetime.now()
        self.end_time = None
        
    def add_result(self, agent_name: str, success: bool, error: Optional[str] = None, 
                   duration: Optional[float] = None, details: Optional[Dict] = None):
        """Add a test result"""
        self.results[agent_name] = {
            "success": success,
            "error": error,
            "duration": duration,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
    
    def get_summary(self) -> Dict:
        """Get the test summary"""
        total = len(self.results)
        successful = sum(1 for r in self.results.values() if r["success"])
        failed = total - successful
        
        self.end_time = datetime.now()
        total_duration = (self.end_time - self.start_time).total_seconds()
        
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "total_duration": total_duration,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat()
        }
    
    def save_report(self, filepath: str):
        """Save the test report to a file"""
        report = {
            "summary": self.get_summary(),
            "results": self.results
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

# Global test results object
test_results = TestResults()


def log_info(msg):
    print(f"{BLUE}[INFO]{NC} {msg}")


def log_success(msg):
    print(f"{GREEN}[SUCCESS]{NC} {msg}")


def log_warning(msg):
    print(f"{YELLOW}[WARNING]{NC} {msg}")


def log_error(msg):
    print(f"{RED}[ERROR]{NC} {msg}")


def run(cmd, check=True, capture_output=False, timeout=None, shell=False):
    """Run a subprocess command. cmd can be list or string."""
    if isinstance(cmd, (list, tuple)):
        display = " ".join(shlex.quote(str(x)) for x in cmd)
    else:
        display = cmd
    log_info(f"Running: {display}")
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        if capture_output:
            return result.stdout
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command returned non-zero exit code: {e.returncode}")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        if check:
            raise
        return e
    except subprocess.TimeoutExpired as e:
        log_warning(f"Command timed out (timeout={timeout}s).")
        if check:
            raise
        return e


def read_env_file(env_path: Path):
    """Simple .env file parser (only handles KEY=VALUE format)"""
    env = {}
    if not env_path.exists():
        return env
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                env[key] = val
    return env


def check_environment():
    """Equivalent check logic to the original check_environment script"""
    log_info("Checking test environment...")
    env_path = Path(".env")
    template_path = Path(".env.template")
    if not env_path.exists():
        log_warning(".env file not found, creating from template...")
        if template_path.exists():
            run(["cp", str(template_path), str(env_path)])
            log_warning("Created .env from .env.template, please edit .env and fill in your API keys")
            return False
        else:
            log_error(".env.template also does not exist, please provide .env or .env.template")
            return False

    env = read_env_file(env_path)
    if not env.get("OPENAI_API_KEY") and not env.get("GEMINI_API_KEY"):
        log_error("At least one of OPENAI_API_KEY or GEMINI_API_KEY must be configured")
        return False

    log_success("Environment check passed")
    return True


def setup_test_environment():
    log_info("Setting up test environment...")

    if not check_environment():
        log_error("Environment configuration failed, please configure the .env file first")
        return 1

    # Build images
    log_info("Building Docker images...")
    run(["docker-compose", "-f", "docker-compose.test.yml", "build"])

    # Start Redis
    log_info("Starting test Redis...")
    run(["docker-compose", "-f", "docker-compose.test.yml", "up", "-d", "redis-test"])

    log_info("Waiting for Redis to be ready...")
    time.sleep(5)

    # Check Redis connection
    try:
        out = run(
            ["docker-compose", "-f", "docker-compose.test.yml", "exec", "-T", "redis-test", "redis-cli", "ping"],
            capture_output=True,
        )
        if "PONG" in out:
            log_success("Redis test environment is ready")
        else:
            log_error("Redis failed to start")
            return 1
    except Exception:
        log_error("Error checking Redis")
        return 1

    # Start test container
    log_info("Starting test container...")
    run(["docker-compose", "-f", "docker-compose.test.yml", "up", "-d", "test-env"])

    log_success("Test environment setup complete")
    log_info("Redis port: localhost:6380")
    log_info("Enter the test container with: docker-compose -f docker-compose.test.yml exec test-env bash")
    return 0


def cleanup_test_environment():
    log_info("Cleaning up test environment...")
    run(["docker-compose", "-f", "docker-compose.test.yml", "down", "-v"])
    log_success("Test environment cleaned up")


def get_poetry_python_path() -> str:
    """Get the Python path from the Poetry virtual environment"""
    try:
        # Try to get the Poetry virtual environment path
        result = subprocess.run(
            ["poetry", "env", "info", "--path"], 
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            venv_path = result.stdout.strip()
            python_path = os.path.join(venv_path, "bin", "python")
            if os.path.exists(python_path):
                return python_path
    except Exception:
        pass
    
    # Fallback to default path
    return "/workspace/.venv/bin/python"

def test_weather_agent() -> Tuple[bool, Optional[str], Dict]:
    """Test the Weather Agent, returns (success_status, error_message, details)"""
    start_time = time.time()
    log_info("Testing Weather Agent...")
    
    try:
        # Get the Python path from the Poetry virtual environment
        python_executable = get_poetry_python_path()

        log_info("Starting Weather Agent...")
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "-d", "test-env", "bash", "-c", f"cd /workspace && PYTHONPATH=/workspace {python_executable} agents/weather/main.py"], check=False)

        log_info("Waiting 30 seconds for the agent to fetch weather data...")
        time.sleep(30)

        log_info("Checking for weather data in Redis...")
        python_check = r"""
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('weather*')
    print(f'Found weather data streams: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'Stream {stream} contains {length} messages')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('Latest message:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
except Exception as e:
    print(f'Error: {e}')
"""
        cmd = ["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "bash", "-c", f"cd /workspace && PYTHONPATH=/workspace {python_executable} -c '{python_check}'"]
        result = run(cmd, check=False)
        
        duration = time.time() - start_time
        details = {"duration": duration, "python_executable": python_executable}
        
        # Check if there is weather data
        if "Found weather data streams" in str(result.stdout) if hasattr(result, 'stdout') else False:
            log_success("Weather Agent test completed")
            return True, None, details
        else:
            error_msg = "No weather data stream found"
            log_error(f"Weather Agent test failed: {error_msg}")
            return False, error_msg, details
            
    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"An error occurred during the test: {str(e)}"
        log_error(f"Weather Agent test failed: {error_msg}")
        return False, error_msg, {"duration": duration, "exception": str(e)}


def test_health_agent():
    log_info("Testing Health Agent...")

    log_info("Adding mock mission data...")
    python_inject = r"""
import redis
import json
from datetime import datetime, timezone

r = redis.Redis(host='redis-test', port=6379, decode_responses=True)

mission_data = {
    'person': {
        'name': 'John Doe',
        'age': 45,
        'gender': 'male',
        'known_conditions': ['diabetes type 2', 'recent back injury'],
        'clothing': 'light jacket, jeans, hiking boots',
        'time_missing': '36 hours',
        'last_seen': 'mountain trail near summit'
    },
    'timestamp': datetime.now(timezone.utc).isoformat()
}

r.xadd('mission.new', {'body': json.dumps({'payload': mission_data})})
print('Mock mission data added')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "bash", "-c", f"cd /workspace && PYTHONPATH=/workspace poetry run python -c '{python_inject}'"], check=False)

    log_info("Starting Health Agent (running for 1 minute)...")
    try:
        # call with timeout similar to `timeout 60 docker-compose ...`
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "bash", "-c", "cd /workspace && PYTHONPATH=/workspace poetry run python agents/health/main.py"], check=False, timeout=60)
    except Exception:
        # ignore timeout or runtime errors like the bash script did with "|| true"
        log_warning("Health Agent had a runtime issue or timed out (ignored), continuing with checks")

    log_info("Checking health assessment results...")
    python_check = r"""
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('health*')
    print(f'Found health assessment streams: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'Stream {stream} contains {length} messages')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('Latest health assessment:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
except Exception as e:
    print(f'Error: {e}')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "bash", "-c", f"cd /workspace && PYTHONPATH=/workspace poetry run python -c '{python_check}'"], check=False)
    log_success("Health Agent test completed")


def test_photo_analysis_agent():
    log_info("Testing Photo Analysis Agent...")

    input_dir = Path("input_images")
    if not input_dir.exists() or not any(input_dir.iterdir()):
        log_warning("input_images directory is empty, creating a test image...")
        input_dir.mkdir(parents=True, exist_ok=True)
        # Attempt to copy an existing image basketball.png -> test_photo.png (consistent with the original script)
        src = input_dir / "basketball.png"
        dst = input_dir / "test_photo.png"
        if src.exists():
            run(["cp", str(src), str(dst)])
            log_info(f"Test image created: {dst}")
        else:
            log_warning("No test image found, please manually add images to the input_images/ directory")
            return 1

    log_info("Starting Photo Analysis Agent (running for 30 seconds)...")
    try:
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "agents/photo_analysis/main.py"], check=False, timeout=30)
    except Exception:
        log_warning("Photo Analysis Agent timed out or had an error (ignored)")

    log_info("Checking image analysis results...")
    python_check = r"""
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('photo*')
    print(f'Found photo analysis streams: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'Stream {stream} contains {length} messages')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('Latest analysis result:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        if 'detections' in parsed:
                            print(f'Detected {len(parsed["detections"])} objects')
                            for det in parsed['detections'][:3]:
                                print(f'  - {det.get("class", "unknown")}: {det.get("confidence", 0):.2f}')
                        if 'person_analysis' in parsed:
                            pa = parsed['person_analysis']
                            print(f'Person analysis: {pa.get("total_people", 0)} people, {pa.get("faces_detected", 0)} faces')
                    except Exception as e:
                        print(f'Parsing error: {e}')
                        print(f'{key}: {str(value)[:100]}...')
except Exception as e:
    print(f'Error: {e}')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "-c", python_check], check=False)
    log_success("Photo Analysis Agent test completed")


def test_interview_agent():
    log_info("Testing Interview Agent...")

    transcripts_dir = Path("data/transcripts")
    pdfs = list(transcripts_dir.glob("*.pdf")) if transcripts_dir.exists() else []
    if not pdfs:
        log_warning("No interview transcript PDF files found")
        log_info("Please place PDF files in the data/transcripts/ directory")
        log_info("Alternatively, we can test other features of the Agent...")

        python_check = r"""
import sys
sys.path.append('/workspace')
# Try to import InterviewAnalystAgent, if it does not exist, only demonstrate text processing logic
try:
    from agents.interview.main import InterviewAnalystAgent
    print('Testing basic functions of Interview Agent...')
    agent = InterviewAnalystAgent(
        name='Test Interview Analyst',
        role='Test role',
        system_message='Test system message'
    )
    test_text = 'I think I saw someone near the trail, but I am not sure about the time.'
    try:
        result = agent.assign_confidence_rating(test_text)
        print(f'Confidence rating result: {result}')
    except Exception as e:
        print('Confidence rating function not available:', e)
    try:
        entities = agent._extract_entities_heuristic(test_text)
        print(f'Entity extraction result: {entities}')
    except Exception as e:
        print('Entity extraction function not available:', e)
    print('Basic function test for Interview Agent completed')
except Exception as e:
    print('Cannot import InterviewAnalystAgent, skipping this test:', e)
"""
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "-c", python_check], check=False)
        return 0

    log_info("Running Interview Agent...")
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "agents/interview/main.py"], check=False)
    log_success("Interview Agent test completed")


def test_logistics_agent():
    log_info("Testing Logistics Agent...")

    log_info("Starting Logistics Agent (running for 30 seconds)...")
    try:
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "agents/logistics/main.py"], check=False, timeout=30)
    except Exception:
        log_warning("Logistics Agent timed out or had an error (ignored)")

    log_info("Checking logistics request data...")
    python_check = r"""
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('logistics*')
    print(f'Found logistics data streams: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'Stream {stream} contains {length} messages')
        if length > 0:
            messages = r.xrevrange(stream, count=3)
            for i, (msg_id, data) in enumerate(messages):
                print(f'Message {i+1}:')
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        print(json.dumps(parsed, indent=2, ensure_ascii=False))
                    except:
                        print(f'{key}: {value}')
                print('---')
except Exception as e:
    print(f'Error: {e}')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "-c", python_check], check=False)
    log_success("Logistics Agent test completed")


def test_path_analysis_agent():
    log_info("Testing Path Analysis Agent...")

    dem_path = Path("agents/path_analysis/data/slo_dem.tif")
    if not dem_path.exists():
        log_warning("DEM terrain data file not found, Path Analysis Agent may not run correctly")
        log_info("Please ensure the file agents/path_analysis/data/slo_dem.tif exists")

    log_info("Running Path Analysis Agent...")
    try:
        run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "agents/path_analysis/main.py"], check=False)
    except Exception:
        log_warning("Path Analysis Agent had a runtime error, possibly due to missing DEM data or dependencies (ignored)")
        return 0

    log_info("Checking path analysis results...")
    python_check = r"""
import redis
import json
r = redis.Redis(host='redis-test', port=6379, decode_responses=True)
try:
    streams = r.keys('path*')
    print(f'Found path analysis streams: {streams}')
    for stream in streams:
        length = r.xlen(stream)
        print(f'Stream {stream} contains {length} messages')
        if length > 0:
            messages = r.xrevrange(stream, count=1)
            if messages:
                print('Path analysis result summary:')
                msg_id, data = messages[0]
                for key, value in data.items():
                    try:
                        parsed = json.loads(value)
                        if 'results' in parsed:
                            results = parsed['results']
                            print(f'Analyzed {len(results)} paths')
                            for i, path in enumerate(results[:3]):
                                print(f'  Path {i+1}: {path.get("summary", "No summary")}')
                    except Exception as e:
                        print(f'Error parsing results: {e}')
except Exception as e:
    print(f'Error: {e}')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "-c", python_check], check=False)
    log_success("Path Analysis Agent test completed")


def view_redis_data():
    log_info("Viewing data in Redis...")
    python_check = r"""
import redis
import json
from datetime import datetime

r = redis.Redis(host='redis-test', port=6379, decode_responses=True)

print('=== Redis Data Overview ===')
try:
    streams = r.keys('*')
    if not streams:
        print('No data in Redis')
        return

    print(f'Found {len(streams)} data streams:')

    for stream in sorted(streams):
        try:
            if stream.endswith('.raw') or 'mission' in stream:
                length = r.xlen(stream)
                print(f'\n{stream}: {length} messages')
                if length > 0:
                    messages = r.xrevrange(stream, count=1)
                    if messages:
                        msg_id, data = messages[0]
                        timestamp = datetime.fromtimestamp(int(msg_id.split('-')[0]) / 1000)
                        print(f'   Latest message time: {timestamp.strftime("%Y-%m-%d %H:%M:%S")}')
                        for key, value in data.items():
                            try:
                                parsed = json.loads(value)
                                if isinstance(parsed, dict):
                                    if 'payload' in parsed:
                                        payload = parsed['payload']
                                        if 'forecasts' in payload:
                                            print(f'   Weather forecast data: {len(payload["forecasts"])} forecasts')
                                        elif 'detections' in payload:
                                            print(f'   Photo analysis: {len(payload["detections"])} detected objects')
                                        elif 'assessment' in payload:
                                            risk = payload['assessment'].get('risk_level', 'UNKNOWN')
                                            print(f'   Health assessment: Risk level {risk}')
                                        elif 'requested_item' in payload:
                                            item = payload['requested_item']
                                            print(f'   Logistics request: {item}')
                                        elif 'results' in payload:
                                            print(f'   Path analysis: {len(payload["results"])} paths')
                                        else:
                                            print(f'   Data type: {list(payload.keys())[:3]}')
                                    else:
                                        print(f'   Data type: {list(parsed.keys())[:3]}')
                            except:
                                print(f'   Raw data: {str(value)[:50]}...')
            else:
                data_type = r.type(stream)
                print(f'\n{stream}: {data_type} type')
        except Exception as e:
            print(f'\nError reading {stream}: {e}')

except Exception as e:
    print(f'Error connecting to Redis: {e}')
"""
    run(["docker-compose", "-f", "docker-compose.test.yml", "exec", "test-env", "python", "-c", python_check], check=False)
    log_info("Tip: Use 'docker-compose -f docker-compose.test.yml exec redis-test redis-cli' to access Redis directly")


def test_all_agents():
    """Test all available agents"""
    log_info("Starting batch test for all Agents...")
    
    # Reset test results
    global test_results
    test_results = TestResults()
    
    # Test function mapping
    test_functions = {
        "weather": test_weather_agent,
        "health": test_health_agent,
        "photo-analysis": test_photo_analysis_agent,
        "interview": test_interview_agent,
        "logistics": test_logistics_agent,
        "path-analysis": test_path_analysis_agent,
    }
    
    for agent_name in AVAILABLE_AGENTS:
        log_info(f"\n{'='*50}")
        log_info(f"Starting test for {agent_name} Agent")
        log_info(f"{'='*50}")
        
        if agent_name in test_functions:
            try:
                success, error, details = test_functions[agent_name]()
                test_results.add_result(agent_name, success, error, details.get("duration"), details)
                
                if success:
                    log_success(f"{agent_name} Agent test passed")
                else:
                    log_error(f"{agent_name} Agent test failed: {error}")
                    
            except Exception as e:
                error_msg = f"Error executing test function: {str(e)}"
                log_error(f"{agent_name} Agent test exception: {error_msg}")
                test_results.add_result(agent_name, False, error_msg, None, {"exception": str(e)})
        else:
            log_warning(f"{agent_name} Agent does not have a corresponding test function")
            test_results.add_result(agent_name, False, "No test function", None, {})
    
    # Generate test report
    log_info(f"\n{'='*50}")
    log_info("Test Result Summary")
    log_info(f"{'='*50}")
    
    summary = test_results.get_summary()
    log_info(f"Total tests: {summary['total']}")
    log_info(f"Successful: {summary['successful']}")
    log_info(f"Failed: {summary['failed']}")
    log_info(f"Success rate: {summary['success_rate']:.1f}%")
    log_info(f"Total duration: {summary['total_duration']:.1f}s")
    
    # Save detailed report
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    test_results.save_report(report_file)
    log_info(f"Detailed report saved to: {report_file}")
    
    # Display failed tests
    failed_agents = [name for name, result in test_results.results.items() if not result["success"]]
    if failed_agents:
        log_warning(f"\nFailed Agents: {', '.join(failed_agents)}")
        for agent in failed_agents:
            error = test_results.results[agent]["error"]
            log_warning(f"  - {agent}: {error}")
    
    return summary["failed"] == 0


def show_help():
    print("SAR Agent Test Tool")
    print()
    print("Usage:")
    print("  ./test_single_agent.py [agent-name]")
    print()
    print("Available Agents:")
    for agent in AVAILABLE_AGENTS:
        print(f"  - {agent}")
    print()
    print("Special Commands:")
    print("  list     - List all available agents")
    print("  setup    - Set up the test environment")
    print("  cleanup  - Clean up the test environment")
    print("  redis    - Start Redis and view data")
    print("  test-all - Batch test all agents")
    print("  report   - Show the latest test report")
    print()
    print("Examples:")
    print("  ./test_single_agent.py setup           # First time use, set up environment")
    print("  ./test_single_agent.py weather         # Test the Weather Agent")
    print("  ./test_single_agent.py test-all        # Batch test all agents")
    print("  ./test_single_agent.py photo-analysis  # Test the Photo Analysis Agent")
    print()


def show_latest_report():
    """Display the latest test report"""
    import glob
    
    # Find the latest test report file
    report_files = glob.glob("test_report_*.json")
    if not report_files:
        log_warning("No test report files found")
        return
    
    latest_report = max(report_files, key=os.path.getctime)
    log_info(f"Displaying latest test report: {latest_report}")
    
    try:
        with open(latest_report, 'r', encoding='utf-8') as f:
            report = json.load(f)
        
        summary = report["summary"]
        log_info(f"\nTest Summary:")
        log_info(f"  Total tests: {summary['total']}")
        log_info(f"  Successful: {summary['successful']}")
        log_info(f"  Failed: {summary['failed']}")
        log_info(f"  Success rate: {summary['success_rate']:.1f}%")
        log_info(f"  Total duration: {summary['total_duration']:.1f}s")
        log_info(f"  Test time: {summary['start_time']}")
        
        # Display details of failed tests
        failed_agents = [name for name, result in report["results"].items() if not result["success"]]
        if failed_agents:
            log_warning(f"\nFailed Agents:")
            for agent in failed_agents:
                error = report["results"][agent]["error"]
                log_warning(f"  - {agent}: {error}")
        
    except Exception as e:
        log_error(f"Failed to read report file: {e}")


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?", default="help")
    args = parser.parse_args()
    cmd = args.command

    try:
        if cmd == "setup":
            setup_test_environment()
        elif cmd == "cleanup":
            cleanup_test_environment()
        elif cmd == "weather":
            success, error, details = test_weather_agent()
            test_results.add_result("weather", success, error, details.get("duration"), details)
        elif cmd == "health":
            test_health_agent()
        elif cmd == "photo-analysis":
            test_photo_analysis_agent()
        elif cmd == "interview":
            test_interview_agent()
        elif cmd == "logistics":
            test_logistics_agent()
        elif cmd == "path-analysis":
            test_path_analysis_agent()
        elif cmd == "redis":
            view_redis_data()
        elif cmd == "test-all":
            success = test_all_agents()
            sys.exit(0 if success else 1)
        elif cmd == "report":
            show_latest_report()
        elif cmd == "list":
            print("Available Agents:")
            for a in AVAILABLE_AGENTS:
                print(f"  - {a}")
        elif cmd in ("help", "-h", "--help"):
            show_help()
        else:
            log_error(f"Unknown command: {cmd}")
            show_help()
            sys.exit(1)
    except KeyboardInterrupt:
        log_warning("Interrupted")
        sys.exit(1)
    except Exception as e:
        log_error(f"Runtime error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()