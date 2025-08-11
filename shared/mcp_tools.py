# shared/mcp_tools.py
"""
Helpers for LLM tool-calling.

Usage:
from shared.mcp_tools import create_tool_use_request, get_tool_call_from_response

# example of defining a tool (JSON Schema)
redis_search_tool = {
    "type": "function",
    "function": {
        "name": "search_past_incidents",
        "description": "Search ISRID for similar incidents.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}

# build the request
req_body = create_tool_use_request(
    conversation=[
        {"role": "user", "content": "Find similar cases for a missing 40-year-old hiker."}
    ],
    tools=[redis_search_tool],
    system_instruction="You are a SAR reasoning agent.",
    provider="openai",                  # or "gemini"
    model="gpt-4.1-nano",              # pass whichever model
)

# pass `req_body` to your LLM client (openai.chat.completions.create(**req_body))

# parse the response
tool_call = get_tool_call_from_response(resp_json, provider="openai")
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Tuple
import logging
logger = logging.getLogger(__name__)

def _utc_now_iso() -> str:
    return (
        datetime.utcnow()
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
# -------- OpenAI --------
def _build_openai_prompt(
    conversation: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    system_instruction: str | None,
    model: str,
) -> Dict[str, Any]:
    messages: List[Dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.extend(conversation)

    return {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "metadata": {
            "request_id": str(uuid.uuid4()),
            "timestamp_utc": _utc_now_iso(),
        },
    }


def _parse_openai_response(
    llm_response: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]] | None:
    try:
        first_choice = llm_response["choices"][0]
        tool_calls = first_choice["message"].get("tool_calls")
        if not tool_calls:
            return None

        call = tool_calls[0]["function"]
        name = call["name"]
        args_raw = call["arguments"]
        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        return name, args
    except (KeyError, IndexError, json.JSONDecodeError):
        return None


# -------- Google Gemini --------
def _build_gemini_prompt(
    conversation: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    system_instruction: str | None,
    model: str,
) -> Dict[str, Any]:
    gemini_tools = [{"function_declarations": [t["function"] for t in tools]}]
    gemini_contents = []
    if system_instruction:
        gemini_contents.append({"role": "user", "parts": [{"text": system_instruction}]})
        gemini_contents.append({"role": "model", "parts": [{"text": "OK, I am ready to act as your SAR reasoning agent."}]})

    for msg in conversation:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    return {
        "contents": gemini_contents,
        "tools": gemini_tools,
    }


def _parse_gemini_response(
    llm_response: Dict[str, Any]
) -> Tuple[str, Dict[str, Any]] | None:
    try:
        candidate = llm_response["candidates"][0]
        part = candidate["content"]["parts"][0]
        
        if "functionCall" not in part:
            return None

        call = part["functionCall"]
        name = call["name"]
        args = call.get("args", {}) 
        return name, args
    except (KeyError, IndexError):
        return None


_DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4.1-nano")
_DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-1.5-flash")

_PROVIDER_MAP = {
    "openai": {
        "build": _build_openai_prompt,
        "parse": _parse_openai_response,
        "default_model": _DEFAULT_OPENAI_MODEL,
    },
    "gemini": {
        "build": _build_gemini_prompt,
        "parse": _parse_gemini_response,
        "default_model": _DEFAULT_GEMINI_MODEL,
    },
}

def create_tool_use_request(
    *,
    conversation: List[Dict[str, str]],
    tools: List[Dict[str, Any]],
    system_instruction: str | None = None,
    provider: Literal["openai", "gemini"] = "openai",
    model: str | None = None,
) -> Dict[str, Any]:
    """
    Parameters
    ----------
    conversation : history so far, list of {role, content}
    tools         : list of tool JSONSchema dicts
    system_instruction : optional system message
    provider      : "openai" | "gemini"
    model         : overrides provider default

    Returns
    -------
    dict : ready to pass to the provider’s chat endpoint
    """
    provider = provider.lower()
    if provider not in _PROVIDER_MAP:
        raise ValueError(f"Unsupported provider '{provider}'")

    builder = _PROVIDER_MAP[provider]["build"]
    chosen_model = model or _PROVIDER_MAP[provider]["default_model"]
    logger.info(f"[MCP Tools] Provider={provider}, Using model={chosen_model}")

    return builder(conversation, tools, system_instruction, chosen_model)


def get_tool_call_from_response(
    llm_response: Dict[str, Any],
    *,
    provider: Literal["openai", "gemini"] = "openai",
) -> Tuple[str, Dict[str, Any]] | None:
    provider = provider.lower()
    if provider not in _PROVIDER_MAP:
        raise ValueError(f"Unsupported provider '{provider}'")

    parser = _PROVIDER_MAP[provider]["parse"]
    return parser(llm_response)
