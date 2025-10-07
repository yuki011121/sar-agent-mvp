#!/usr/bin/env python3
"""
Test script for Interview Analysis Agent
"""

import json
import time
from shared import RedisBus, wrap_envelope

def test_interview_agent():
    """Test the interview agent with sample data"""
    
    # Sample interview transcript
    sample_transcript = """
    Interview with John Smith - Witness to Missing Person Case
    
    Q: Can you tell me what you saw yesterday evening?
    A: I was walking my dog around 7 PM near the hiking trail. I definitely saw a person matching the description - about 5'8", wearing a red jacket and blue jeans. They were heading towards the mountain trail.
    
    Q: Did you notice anything unusual about their behavior?
    A: Well, they seemed to be in a hurry. I'm not sure, but they might have been looking for something. I think they had a backpack with them.
    
    Q: What time exactly did you see them?
    A: It was around 7:15 PM, I'm pretty sure. I remember because I was checking my watch to see if it was time to head home.
    
    Q: Did you see anyone else in the area?
    A: No, it was pretty quiet. I didn't see any other hikers or vehicles in the parking lot.
    
    Q: Can you describe the person's appearance in more detail?
    A: They had dark hair, I think. Maybe brown or black. I couldn't see their face clearly because they were wearing a hat. The red jacket was very noticeable though.
    """
    
    # Create test message
    test_payload = {
        "transcript_text": sample_transcript,
        "case_id": "TEST-001",
        "witness_name": "John Smith",
        "interview_date": "2025-10-05"
    }
    
    # Connect to Redis
    bus = RedisBus("redis://localhost:6379")
    
    # Create and send message
    message = wrap_envelope(
        payload=test_payload,
        source_name="test-client",
        source_version="1.0",
        target_stream="interview.in.raw"
    )
    
    print("Sending test interview request...")
    bus.publish(message)
    
    # Wait a bit for processing
    print("Waiting for processing...")
    time.sleep(5)
    
    # Check for results using Redis CLI
    print("Checking for results...")
    import subprocess
    try:
        result = subprocess.run([
            "docker", "exec", "147be75d00bf", "redis-cli", 
            "XREAD", "STREAMS", "interview.analysis.raw", "0"
        ], capture_output=True, text=True, timeout=10)
        
        if result.stdout:
            print("Received result:")
            print(result.stdout)
        else:
            print("No results found")
    except Exception as e:
        print(f"Error checking results: {e}")

if __name__ == "__main__":
    test_interview_agent()
