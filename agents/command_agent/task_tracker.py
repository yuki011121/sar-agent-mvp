#!/usr/bin/env python3
"""
Task Tracker for SAR Command Agent

Manages task dispatch and response tracking for multi-agent coordination.
Tasks are published to agent input streams and responses are collected
from output streams with task_id correlation.
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

import redis

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEFAULT_TIMEOUT = int(os.getenv("TASK_TIMEOUT_SECONDS", 60))

logger = logging.getLogger("command-agent-task-tracker")


@dataclass
class Task:
    """Represents a dispatched task."""
    task_id: str
    target_stream: str
    output_stream: str
    payload: Dict[str, Any]
    status: str = "pending"  # pending, done, error, timeout
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class TaskTracker:
    """
    Tracks tasks dispatched to specialist agents and collects their responses.
    
    Usage:
        tracker = TaskTracker()
        
        # Submit tasks
        task_id = tracker.submit_task(
            target_stream="history.in.raw",
            output_stream="history.out.raw",
            payload={"query": "similar cases with elderly dementia"}
        )
        
        # Wait for results
        results = tracker.wait_for_tasks([task_id], timeout=30)
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or REDIS_URL
        self.redis_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        self.pending_tasks: Dict[str, Task] = {}
        
        # Verify connection
        self.redis_client.ping()
        logger.info("TaskTracker initialized")
    
    def generate_task_id(self) -> str:
        """Generate a unique task ID."""
        return f"TASK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    
    def submit_task(
        self,
        target_stream: str,
        output_stream: str,
        payload: Dict[str, Any],
        task_id: Optional[str] = None
    ) -> str:
        """
        Submit a task to an agent's input stream.
        
        Args:
            target_stream: The Redis stream to publish to (e.g., "history.in.raw")
            output_stream: The stream where agent publishes results (e.g., "history.out.raw")
            payload: The task payload (will have task_id added)
            task_id: Optional custom task_id, auto-generated if not provided
            
        Returns:
            task_id: The task identifier for tracking
        """
        task_id = task_id or self.generate_task_id()
        
        # Add task_id to payload
        task_payload = {
            **payload,
            "task_id": task_id,
            "submitted_at": datetime.utcnow().isoformat() + "Z",
            "requester": "command-agent"
        }
        
        # Create task record
        task = Task(
            task_id=task_id,
            target_stream=target_stream,
            output_stream=output_stream,
            payload=task_payload
        )
        
        # Store in Redis for persistence (optional, for debugging)
        self.redis_client.hset(
            f"task:{task_id}",
            mapping={
                "status": "pending",
                "target_stream": target_stream,
                "output_stream": output_stream,
                "payload": json.dumps(task_payload),
                "created_at": task.created_at.isoformat()
            }
        )
        self.redis_client.expire(f"task:{task_id}", 3600)  # 1 hour TTL
        
        # Publish to target stream using StandardMessage envelope
        try:
            from shared import wrap_envelope
            message = wrap_envelope(
                payload=task_payload,
                source_name="command-agent",
                source_version="2.0",
                target_stream=target_stream
            )
            # Extract body for XADD
            body = message.model_dump_json() if hasattr(message, 'model_dump_json') else json.dumps(message)
            self.redis_client.xadd(target_stream, {"body": body})
        except ImportError:
            # Fallback: direct publish
            self.redis_client.xadd(target_stream, {"body": json.dumps({"payload": task_payload})})
        
        # Track locally
        self.pending_tasks[task_id] = task
        
        logger.info(f"Task submitted: {task_id} → {target_stream}")
        return task_id
    
    def check_task_result(self, task_id: str, output_stream: str) -> Optional[Dict[str, Any]]:
        """
        Check if a task has completed by scanning the output stream.
        
        Args:
            task_id: The task ID to look for
            output_stream: The stream to check
            
        Returns:
            Result payload if found, None otherwise
        """
        try:
            # Get recent messages from the output stream
            messages = self.redis_client.xrevrange(output_stream, count=50)
            
            for msg_id, data in messages:
                try:
                    # Parse the message
                    body = data.get("body", "{}")
                    if isinstance(body, str):
                        parsed = json.loads(body)
                    else:
                        parsed = body
                    
                    # Extract payload
                    payload = parsed.get("payload", parsed)
                    
                    # Check if this is our task's response
                    if payload.get("task_id") == task_id:
                        logger.info(f"Task result found: {task_id}")
                        return payload
                        
                except (json.JSONDecodeError, AttributeError) as e:
                    continue
                    
        except Exception as e:
            logger.error(f"Error checking task result: {e}")
        
        return None
    
    def wait_for_tasks(
        self,
        task_ids: List[str],
        timeout: int = DEFAULT_TIMEOUT,
        poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """
        Wait for multiple tasks to complete.
        
        Args:
            task_ids: List of task IDs to wait for
            timeout: Maximum time to wait in seconds
            poll_interval: How often to poll for results
            
        Returns:
            Dict mapping task_id to result (or error message)
        """
        results = {}
        deadline = time.time() + timeout
        remaining_tasks = set(task_ids)
        
        logger.info(f"Waiting for {len(task_ids)} tasks (timeout: {timeout}s)")
        
        while time.time() < deadline and remaining_tasks:
            for task_id in list(remaining_tasks):
                task = self.pending_tasks.get(task_id)
                if not task:
                    # Try to get task info from Redis
                    task_data = self.redis_client.hgetall(f"task:{task_id}")
                    if task_data:
                        output_stream = task_data.get("output_stream", "")
                    else:
                        results[task_id] = {"error": "Task not found"}
                        remaining_tasks.discard(task_id)
                        continue
                else:
                    output_stream = task.output_stream
                
                # Check for result
                result = self.check_task_result(task_id, output_stream)
                if result:
                    results[task_id] = result
                    remaining_tasks.discard(task_id)
                    
                    # Update task status
                    if task:
                        task.status = "done"
                        task.result = result
                        task.completed_at = datetime.utcnow()
                    
                    self.redis_client.hset(f"task:{task_id}", "status", "done")
            
            if remaining_tasks:
                time.sleep(poll_interval)
        
        # Mark remaining tasks as timeout
        for task_id in remaining_tasks:
            results[task_id] = {"error": "timeout", "message": f"Task {task_id} timed out after {timeout}s"}
            if task_id in self.pending_tasks:
                self.pending_tasks[task_id].status = "timeout"
            self.redis_client.hset(f"task:{task_id}", "status", "timeout")
        
        logger.info(f"Tasks completed: {len(task_ids) - len(remaining_tasks)}/{len(task_ids)}")
        return results
    
    def get_task_status(self, task_id: str) -> str:
        """
        Get the current status of a task.
        
        Returns: "pending", "done", "error", "timeout", or "not_found"
        """
        # Check local cache first
        if task_id in self.pending_tasks:
            return self.pending_tasks[task_id].status
        
        # Check Redis
        status = self.redis_client.hget(f"task:{task_id}", "status")
        return status or "not_found"
    
    def clear_completed_tasks(self):
        """Clear completed tasks from local tracking."""
        to_remove = [
            task_id for task_id, task in self.pending_tasks.items()
            if task.status in ("done", "error", "timeout")
        ]
        for task_id in to_remove:
            del self.pending_tasks[task_id]
        logger.info(f"Cleared {len(to_remove)} completed tasks")


# Stream mapping for agents
AGENT_STREAMS = {
    "history": {
        "input": "history.in.raw",
        "output": "history.out.raw"
    },
    "interview": {
        "input": "interview.in.raw",
        "output": "interview.analysis.raw"
    },
    "photo": {
        "input": "photo.task.raw",
        "output": "photo.analysis.raw"
    },
    "weather": {
        "input": "weather.query.raw",
        "output": "weather.forecast.raw"
    },
    "health": {
        "input": "health.assess.raw",
        "output": "health.assessment.raw"
    },
    "path": {
        "input": "path.query.raw",
        "output": "path.analysis.raw"
    },
    "logistics": {
        "input": "logistics.query.raw",
        "output": "logistics.status.raw"
    }
}


def get_agent_streams(agent_name: str) -> tuple:
    """Get input/output streams for an agent."""
    streams = AGENT_STREAMS.get(agent_name)
    if streams:
        return streams["input"], streams["output"]
    raise ValueError(f"Unknown agent: {agent_name}")


# Global tracker instance (lazy-loaded)
_tracker: Optional[TaskTracker] = None


def get_tracker() -> TaskTracker:
    """Get or create the global TaskTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = TaskTracker()
    return _tracker
