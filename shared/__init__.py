# shared/__init__.py
# Flexible stubs so agents.weather.main can import and publish during tests.

from __future__ import annotations
from typing import Any, Dict
import json

def _to_text(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("content", "message", "text", "summary", "advisory", "desc"):
            v = x.get(k)
            if isinstance(v, str):
                return v
        return json.dumps(x, ensure_ascii=False)
    return str(x)

def wrap_envelope(*args, **kwargs) -> Dict[str, Any]:
    """
    Support BOTH call styles:
      - wrap_envelope(source, content, **extra)
      - wrap_envelope(payload=..., target_stream=..., source=..., ...)
    Always returns a dict with a readable 'content' field.
    """
    env: Dict[str, Any] = {}

    # Positional style: (source, content)
    if len(args) >= 2:
        source, content = args[0], args[1]
        env["source"] = source
        env["content"] = _to_text(content)
        env.update(kwargs)
        # keep payload if provided via kwargs
        if "payload" in kwargs:
            env["payload"] = kwargs["payload"]
        return env

    # Keyword style: expect payload and optional source/stream/etc.
    payload = kwargs.pop("payload", None)
    source = kwargs.pop("source", "weather-agent")
    env["source"] = source
    # prefer content inside payload; otherwise stringify payload
    if payload is not None:
        env["payload"] = payload
        env["content"] = _to_text(payload)
    else:
        # if caller passed content=... directly
        content_kw = kwargs.pop("content", "")
        env["content"] = _to_text(content_kw)
    # copy remaining fields like target_stream, agent, timestamp, etc.
    env.update(kwargs)
    return env

class RedisBus:
    """Stub bus; real tests inject their own FakeBus."""
    def __init__(self, url: str | None = None) -> None:
        self.url = url
    def publish(self, *args, **kwargs):
        pass

