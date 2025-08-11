# shared/a2a_envelope.py
"""
This module provides the standardized message envelope for all A2A communication within the system.
Wrap payloads in a single, validated structure that every agent publishes to Redis.  Down-stream code only ever has to read:
    msg["envelope"] → routing / trace info
    msg["payload"]  → business data
"""
import uuid
import json
import logging
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
class SourceAgent(BaseModel):
    name: str
    version: str
class Envelope(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_agent: SourceAgent
    target_stream: str
class StandardMessage(BaseModel):
    envelope: Envelope
    payload: dict
def wrap_envelope(payload: dict, source_name: str, source_version: str, target_stream: str) -> StandardMessage:
    source_agent_obj = SourceAgent(name=source_name, version=source_version)
    envelope_obj = Envelope(source_agent=source_agent_obj, target_stream=target_stream)
    message = StandardMessage(envelope=envelope_obj, payload=payload)
    return message
def parse_message_from_stream(stream_data: dict) -> StandardMessage | None:
    """
    Parses and validates an incoming message from a Redis Stream.
    Assumes the message is stored in a field named 'body'.
    """
    if "body" not in stream_data:
        logging.error("Message data does not contain 'body' field.")
        return None
    try:
        message_obj = StandardMessage.model_validate_json(stream_data["body"])
        return message_obj
    except (ValidationError, json.JSONDecodeError) as e:
        logging.error(f"Failed to parse or validate incoming message: {e}")
        return None