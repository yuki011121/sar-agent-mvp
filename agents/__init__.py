# agents/weather/__init__.py
"""
Adapter so test harness can call the weather agent in this package, even if
the main logic lives in agents/weather/main.py as a class or a function.
"""

from __future__ import annotations
import inspect
from typing import Any

def _to_text(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("output", "response", "answer", "text", "message", "content"):
            if k in x:
                return str(x[k])
    return str(x)

def run(prompt: str, context: str | None = None) -> str:
    """
    Entry point the harness will call: agents.weather:run(prompt, context)
    Tries several common patterns inside agents/weather/main.py:
      - WeatherAgent class with respond()/run()/handle()/__call__()
      - Top-level functions respond/run/handle/main/generate/infer
    """
    # Import your module that contains the real agent logic
    try:
        from . import main as impl
    except Exception as e:
        raise RuntimeError(f"Could not import agents.weather.main: {e}")

    # 1) Try a class named WeatherAgent
    agent_cls = getattr(impl, "WeatherAgent", None)
    if inspect.isclass(agent_cls):
        try:
            agent = agent_cls()  # no-arg init; adjust if yours needs args
        except Exception as e:
            raise RuntimeError(f"WeatherAgent() failed to initialize: {e}")

        for method in ("respond", "run", "handle", "__call__", "generate"):
            if hasattr(agent, method):
                fn = getattr(agent, method)
                try:
                    sig = inspect.signature(fn)
                    if len(sig.parameters) >= 2:
                        return _to_text(fn(prompt, context))
                    else:
                        return _to_text(fn(prompt))
                except Exception as e:
                    raise RuntimeError(f"WeatherAgent.{method}() raised: {e}")

    # 2) Try common top-level functions
    for name in ("respond", "run", "handle", "main", "generate", "infer"):
        fn = getattr(impl, name, None)
        if callable(fn):
            try:
                sig = inspect.signature(fn)
                if len(sig.parameters) >= 2:
                    return _to_text(fn(prompt, context))
                else:
                    return _to_text(fn(prompt))
            except Exception as e:
                raise RuntimeError(f"Function {name}() raised: {e}")

    # 3) Nothing matched
    raise RuntimeError(
        "agents.weather.main did not expose a usable class or function. "
        "Expected WeatherAgent.[respond|run|handle|__call__] or "
        "[respond|run|handle|main|generate|infer](prompt, [context])."
    )

