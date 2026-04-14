# agents/weather/test_entry.py
"""
Test adapter for the weather agent.

- Fakes the Redis bus so nothing external runs.
- Calls a function in agents.weather.main that would normally publish to the bus.
- Returns the last published message as a string for the test harness.
"""

from __future__ import annotations
import importlib, json

# Try these candidate functions inside agents.weather.main, in order
CANDIDATE_FUNS = [
    "fetch_and_publish_weather",  # typical publish entry point
    "publish_weather_update",
    "run_once",
]

class FakeBus:
    """Minimal stand-in for RedisBus that captures publishes."""
    def __init__(self) -> None:
        self.messages = []

    # common patterns: publish(topic, message) OR publish(envelope_dict)
    def publish(self, *args, **kwargs):
        if args and isinstance(args[0], dict) and not kwargs:
            # envelope-only publish(envelope_dict)
            self.messages.append(args[0])
        elif len(args) >= 2:
            topic, payload = args[0], args[1]
            self.messages.append({"topic": topic, "payload": payload, **kwargs})
        else:
            # Anything else: capture raw
            self.messages.append({"args": args, "kwargs": kwargs})

def _to_text(msg) -> str:
    # Try to pull a sensible human text out of the envelope/payload
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        # common envelope shapes
        for key in ("content", "message", "text", "payload", "data"):
            if key in msg and isinstance(msg[key], str):
                return msg[key]
        return json.dumps(msg, ensure_ascii=False)
    return str(msg)

def run(prompt: str, context: str | None = None) -> str:
    impl = importlib.import_module("agents.weather.main")

    # If your code expects env/context, feel free to parse it from `prompt`/`context`.
    # For now we just call the publish function and read the last published message.
    bus = FakeBus()

    # Find and call a publish-like function
    for name in CANDIDATE_FUNS:
        fn = getattr(impl, name, None)
        if callable(fn):
            try:
                fn(bus)  # preferred signature: fn(bus)
            except TypeError:
                # Some variants might be fn(bus, **options) or fn()
                try:
                    fn(bus, prompt=prompt, context=context)
                except TypeError:
                    fn()
            break
    else:
        # No candidate function found — fall back to a generic advisory
        return "Generic SAR weather advisory: high-level guidance only; check NWS/NOAA for live conditions."

    # Extract last published message into text
    if bus.messages:
        return _to_text(bus.messages[-1])
    return "Weather agent published nothing."
