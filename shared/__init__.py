# shared/__init__.py
# Flexible stubs so agents.weather.main can import and publish during tests.

from __future__ import annotations
from typing import Any, Dict
import json

def _to_text(x: Any) -> str:
    # 1) If it's a string, try to parse JSON first; otherwise return as-is
    if isinstance(x, str):
        s = x.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                import json as _json
                return _to_text(_json.loads(s))  # recurse with parsed object
            except Exception:
                pass
        return x

    # helper: summarize a list of period-like dicts (NWS-style)
    def _summarize_periods(periods):
        lines = []
        for p in periods[:2]:  # summarize the first two
            if not isinstance(p, dict):
                continue
            name = p.get("name") or (f"Period {p.get('number','')}")
            temp = p.get("temperature")
            tu = p.get("temperatureUnit", "F")
            wind = f"{p.get('windDirection','')} {p.get('windSpeed','')}".strip()
            pop_val = None
            pop = p.get("probabilityOfPrecipitation")
            if isinstance(pop, dict):
                pop_val = pop.get("value")
            short = p.get("shortForecast") or ""
            bits = [f"{name}: {short}"]
            if temp is not None:
                bits.append(f"{temp}{tu}")
            if wind:
                bits.append(f"wind {wind}")
            if isinstance(pop_val, (int, float)):
                bits.append(f"PoP {int(pop_val)}%")
            lines.append(", ".join(bits) + ".")
        if lines:
            return " ".join(lines) + " Check NWS/NOAA for decisions."
        return ""

    # 2) NWS official shape: {"properties":{"periods":[...]}}
    if isinstance(x, dict) and isinstance(x.get("properties"), dict):
        periods = x["properties"].get("periods") or []
        text = _summarize_periods(periods)
        if text:
            return text

    # 3) Your agent's shape: {"forecasts":[...]} with period-like entries
    if isinstance(x, dict) and isinstance(x.get("forecasts"), list):
        text = _summarize_periods(x["forecasts"])
        if text:
            return text

    # 4) Generic dicts: try common text fields; else stringify
    if isinstance(x, dict):
        for k in ("content", "message", "text", "summary", "advisory", "desc",
                  "detailedForecast", "shortForecast"):
            v = x.get(k)
            if isinstance(v, str) and v.strip():
                return v
        import json as _json
        return _json.dumps(x, ensure_ascii=False)

    # 5) Fallback
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

