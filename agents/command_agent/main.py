#!/usr/bin/env python3
"""
Command Agent - SAR System Commander
Using LangGraph for multi-agent orchestration

This is the main entry point for the Command Agent. It can run in two modes:
1. Service mode: Continuously listens to command.query.raw stream
2. Interactive mode: Accepts queries from command line

The agent uses a LangGraph state machine to coordinate specialist agents
(weather, health, history, photo, path) and synthesize responses.
"""

import os
import sys
import json
import time
import logging
import uuid
from typing import Optional, List
from datetime import datetime

import redis
from dotenv import load_dotenv

load_dotenv()

# Import shared utilities
from shared import RedisBus, wrap_envelope, parse_message_from_stream

# Import the LangGraph components
from .graph import run_query, sar_graph, get_session_history

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENT_NAME = "command-agent"
AGENT_VERSION = "command-agent-v2.0"  # v2.0 = LangGraph version

# Streams
INPUT_STREAM = "command.query.raw"
OUTPUT_STREAM = "command.response.raw"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


class CommandAgent:
    """
    SAR Command Agent - Orchestrates specialist agents using LangGraph.
    
    Modes:
    - Service: Listens to Redis stream for queries
    - Interactive: Accepts queries from stdin with session persistence
    """
    
    def __init__(self):
        self.bus = RedisBus(REDIS_URL)
        self.redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        self.last_id = "0"  # Track last processed message ID
        self.current_session_id = None  # Current session for interactive mode
        
        # Verify Redis connection
        self.redis_client.ping()
        logger.info(f"✓ Redis connected at {REDIS_URL}")
        logger.info(f"✓ {AGENT_NAME} {AGENT_VERSION} initialized")
    
    def process_query(self, query: str, session_id: Optional[str] = None,
                      file_urls: Optional[list] = None, verbose: bool = False) -> str:
        """
        Process a user query through the LangGraph.

        Args:
            query: User's question
            session_id: Session ID for multi-turn conversations
            file_urls: Uploaded file context (images, PDFs) from API Gateway
            verbose: Whether to log intermediate steps

        Returns:
            Synthesized response from all specialists
        """
        logger.info(f"Processing query: {query[:100]}...")
        start_time = time.time()
        
        try:
            response = run_query(query, session_id=session_id,
                                 file_urls=file_urls, verbose=verbose)
            elapsed = time.time() - start_time
            logger.info(f"Query processed in {elapsed:.2f}s")
            return response
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return f"Error processing query: {str(e)}"

    def publish_response(self, query_id: str, query: str, response: str,
                         session_id: Optional[str] = None,
                         agents_used: Optional[list] = None):
        """Publish response to output stream."""
        payload = {
            "query_id": query_id,
            "query": query,
            "response": response,
            "session_id": session_id,
            "agents_used": agents_used or [],
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "agent_version": AGENT_VERSION,
        }
        
        message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=OUTPUT_STREAM
        )
        
        self.bus.publish(message)
        logger.info(f"Response published to {OUTPUT_STREAM}")
    
    def parse_query_message(self, data: dict) -> Optional[dict]:
        """Parse incoming query message."""
        try:
            parsed = parse_message_from_stream(data)
            if parsed and hasattr(parsed, 'payload'):
                return parsed.payload
            elif isinstance(parsed, dict):
                return parsed.get('payload', parsed)
            return None
        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            return None
    
    def run_service_mode(self):
        """
        Run in service mode - continuously listen for queries on Redis stream.
        """
        logger.info(f"Starting service mode...")
        logger.info(f"Listening on: {INPUT_STREAM}")
        logger.info(f"Publishing to: {OUTPUT_STREAM}")
        
        while True:
            try:
                # Read new messages with blocking
                messages = self.redis_client.xread(
                    {INPUT_STREAM: self.last_id},
                    count=1,
                    block=5000  # 5 second timeout
                )
                
                if not messages:
                    continue
                
                for stream_name, stream_messages in messages:
                    for msg_id, data in stream_messages:
                        logger.info(f"Received query: {msg_id}")
                        
                        # Parse the message
                        query_data = self.parse_query_message(data)
                        if not query_data:
                            logger.warning(f"Invalid query format: {data}")
                            self.last_id = msg_id
                            continue
                        
                        # Extract query text, session, and file context
                        query = query_data.get("query") or query_data.get("question") or str(query_data)
                        query_id = query_data.get("id", msg_id)
                        session_id = query_data.get("session_id")
                        file_urls = query_data.get("file_urls", [])

                        # Process query (active dispatch mode)
                        response = self.process_query(
                            query, session_id=session_id, file_urls=file_urls
                        )

                        # Retrieve which agents were dispatched from graph state
                        agents_used: list = []
                        try:
                            config = {"configurable": {"thread_id": session_id or "default"}}
                            final_state = sar_graph.get_state(config)
                            if final_state:
                                agents_used = final_state.values.get("dispatched_to", []) or []
                        except Exception as _e:
                            logger.debug(f"Could not retrieve dispatched_to from state: {_e}")

                        self.publish_response(
                            query_id, query, response,
                            session_id=session_id, agents_used=agents_used
                        )
                        
                        # Update last processed ID
                        self.last_id = msg_id
                        
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in service loop: {e}", exc_info=True)
                time.sleep(5)
    
    def run_interactive_mode(self):
        """
        Run in interactive mode - accept queries from command line.
        Supports multi-turn conversations with session persistence.
        """
        logger.info("Starting interactive mode...")
        
        # Initialize session
        self.current_session_id = str(uuid.uuid4())
        
        print("\n" + "=" * 60)
        print("SAR Command Agent - Interactive Mode (Multi-Turn)")
        print("=" * 60)
        print(f"Session ID: {self.current_session_id[:8]}...")
        print("\nCommands:")
        print("  <question>   - Ask a question (uses current session)")
        print("  new          - Start a new session")
        print("  history      - Show conversation history")
        print("  session <id> - Switch to an existing session")
        print("  verbose      - Toggle verbose output")
        print("  status       - Show current session info")
        print("  exit/quit    - Exit the program")
        print("=" * 60 + "\n")
        
        verbose = False
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Goodbye!")
                    break
                
                if user_input.lower() == 'new':
                    self.current_session_id = str(uuid.uuid4())
                    print(f"\n✓ New session started: {self.current_session_id[:8]}...\n")
                    continue
                
                if user_input.lower() == 'history':
                    history = get_session_history(self.current_session_id)
                    if history:
                        print("\n--- Conversation History ---")
                        for i, msg in enumerate(history, 1):
                            role = "You" if msg["role"] == "user" else "Assistant"
                            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
                            print(f"{i}. [{role}]: {content}")
                        print("---\n")
                    else:
                        print("\nNo conversation history yet.\n")
                    continue
                
                if user_input.lower().startswith('session '):
                    new_session = user_input[8:].strip()
                    if new_session:
                        self.current_session_id = new_session
                        print(f"\n✓ Switched to session: {self.current_session_id[:8]}...\n")
                    else:
                        print("\nUsage: session <session_id>\n")
                    continue
                
                if user_input.lower() == 'verbose':
                    verbose = not verbose
                    print(f"\nVerbose mode: {'ON' if verbose else 'OFF'}\n")
                    continue
                
                if user_input.lower() == 'status':
                    history = get_session_history(self.current_session_id)
                    print(f"\n--- Session Status ---")
                    print(f"Session ID: {self.current_session_id}")
                    print(f"Messages in history: {len(history)}")
                    print(f"Verbose mode: {'ON' if verbose else 'OFF'}")
                    print("---\n")
                    continue
                
                # Process query with current session
                print("\nProcessing...\n")
                response = self.process_query(user_input, session_id=self.current_session_id, verbose=verbose)
                print(f"\nAssistant: {response}\n")
                print("-" * 60 + "\n")
                
            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except EOFError:
                break
    
    def run_single_query(self, query: str, session_id: Optional[str] = None, verbose: bool = False) -> str:
        """
        Run a single query and return the response.
        Useful for testing or one-off queries.
        
        Args:
            query: The question to ask
            session_id: Optional session ID for context
            verbose: Whether to show intermediate steps
        """
        return self.process_query(query, session_id=session_id, verbose=verbose)
    
    def get_status(self) -> dict:
        """Get agent status information."""
        return {
            "name": AGENT_NAME,
            "version": AGENT_VERSION,
            "framework": "LangGraph",
            "input_stream": INPUT_STREAM,
            "output_stream": OUTPUT_STREAM,
            "status": "ready",
            "redis_connected": True,
            "current_session": self.current_session_id,
            "features": ["multi-turn-conversations", "session-persistence"],
        }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SAR Command Agent")
    parser.add_argument(
        "--mode", 
        choices=["service", "interactive", "cli", "json-io", "query"],
        default="service",
        help="Run mode: service (listen to stream), interactive (simple CLI), cli (rich CLI), json-io (JSON stdin/stdout), query (single query)"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Query to run in query mode"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info(f"Command Agent {AGENT_VERSION} - Starting...")
    logger.info("=" * 60)
    
    try:
        agent = CommandAgent()
        
        if args.mode == "service":
            agent.run_service_mode()
        elif args.mode == "interactive":
            agent.run_interactive_mode()
        elif args.mode == "cli":
            # Rich CLI mode
            try:
                from .cli import run_rich_cli
                run_rich_cli(agent)
            except ImportError as e:
                logger.warning(f"Rich CLI not available ({e}), falling back to interactive mode")
                agent.run_interactive_mode()
        elif args.mode == "json-io":
            # JSON I/O mode for frontend testing
            try:
                from .cli import run_json_io
                run_json_io(agent)
            except ImportError as e:
                logger.error(f"JSON I/O mode requires cli module: {e}")
                sys.exit(1)
        elif args.mode == "query":
            if not args.query:
                print("Error: --query is required in query mode")
                sys.exit(1)
            response = agent.run_single_query(args.query, verbose=args.verbose)
            print(f"\nResponse:\n{response}")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
