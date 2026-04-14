# eval/local_adapter_weather.py
import importlib

# We’ll try a few common function names inside agents.weather
CANDIDATE_FUNS = ["run", "handle", "respond", "main", "invoke"]

def run(prompt: str, context: str | None = None) -> str:
    """
    Adapter so our test harness can call your weather agent code, no matter what
    the function is called or what it returns.
    """
    mod = importlib.import_module("agents.weather")

    # Find a callable in agents.weather
    for name in CANDIDATE_FUNS:
        fn = getattr(mod, name, None)
        if callable(fn):
            out = fn(prompt, context)

            # Normalize common return types to a string
            if isinstance(out, str):
                return out
            if isinstance(out, dict):
                for k in ("output", "response", "answer", "text", "message", "content"):
                    if k in out:
                        return str(out[k])
            # Fallback: stringify whatever was returned
            return str(out)

    raise RuntimeError(
        "No callable found in agents.weather. Tried: " + ", ".join(CANDIDATE_FUNS)
    )
