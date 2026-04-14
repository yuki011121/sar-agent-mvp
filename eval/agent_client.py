# eval/agent_client.py
import os
import time
import requests
import importlib, json, pathlib, sys


MODE = os.getenv("AGENT_MODE", "http_json")  # "http_json" | "echo" | "azure_agents"

def _env_first(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None

def call_agent(prompt: str, context: str | None = None, session: requests.Session | None = None) -> str:
    """
    Returns the agent's text output.

    Modes:
      - echo:         local stub that just echoes the prompt.
      - http_json:    POST to AGENT_URL with body {"input": prompt, "context": "..."}; optional Bearer token.
      - azure_agents: Calls Azure AI Foundry Agents REST: create thread -> add message -> run -> poll -> read reply.
                      Requires env:
                        PROJECT_ENDPOINT  (or AZURE_AI_FOUNDRY_PROJECT_ENDPOINT)
                        AGENT_ID
                        AGENT_TOKEN       (Project API key or bearer token)
                        API_VERSION       (default: v1)
    """
    if MODE == "echo":
        return f"ECHO: {prompt[:200]}"

    if MODE == "http_json":
        url = os.environ["AGENT_URL"]
        key = os.getenv("AGENT_API_KEY", "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"input": prompt}
        if context:
            payload["context"] = context
        sess = session or requests
        resp = sess.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        for k in ("output", "response", "answer", "text"):
            if isinstance(data, dict) and k in data:
                return str(data[k])
        return str(data)

    if MODE == "azure_agents":
        base = _env_first("PROJECT_ENDPOINT", "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
        if not base:
            raise RuntimeError("Set PROJECT_ENDPOINT (from Azure AI Foundry Project → Endpoints and keys).")
        base = base.rstrip("/")

        api_version = os.getenv("API_VERSION", "v1")
        agent_id = _env_first("AGENT_ID", "ASSISTANT_ID")
        if not agent_id:
            raise RuntimeError("Set AGENT_ID (copy from your Agent details in the project).")

        # --- auth: prefer AAD bearer; fallback to project API key ---
        bearer = os.getenv("AGENT_BEARER_TOKEN")
        api_key = _env_first("AGENT_TOKEN", "PROJECT_API_KEY", "API_KEY")

        if bearer:
            headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}
        elif api_key:
            headers = {"api-key": api_key, "Content-Type": "application/json"}
        else:
            raise RuntimeError("Set AGENT_BEARER_TOKEN (preferred) or AGENT_TOKEN/PROJECT_API_KEY.")

        sess = session or requests 
        # 1) Create a thread
        r = sess.post(f"{base}/threads", params={"api-version": api_version}, json={}, headers=headers, timeout=60)
        r.raise_for_status()
        thread_id = r.json()["id"]

        # 2) Add user message (context appended if provided)
        message_content = prompt if not context else f"{prompt}\n\n[context]\n{context}"
        r = sess.post(
            f"{base}/threads/{thread_id}/messages",
            params={"api-version": api_version},
            json={"role": "user", "content": message_content},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()

        # 3) Run the thread with your agent
        r = sess.post(
            f"{base}/threads/{thread_id}/runs",
            params={"api-version": api_version},
            json={"assistant_id": agent_id},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        run = r.json()
        run_id = run["id"]
        status = run.get("status", "in_progress")

        # 4) Poll until completed (or terminal)
        terminal = {"completed", "failed", "cancelled", "expired"}
        for _ in range(120):  # up to ~2 minutes
            if status in terminal:
                break
            if status == "requires_action":
                # For smoke tests we don't resolve tools; bail with a clear error
                raise RuntimeError("Run requires tool outputs; add tools or use a simpler prompt for smoke tests.")
            time.sleep(1)
            r = sess.get(
                f"{base}/threads/{thread_id}/runs/{run_id}",
                params={"api-version": api_version},
                headers=headers,
                timeout=60,
            )
            r.raise_for_status()
            status = r.json().get("status", "in_progress")

        if status != "completed":
            raise RuntimeError(f"Run did not complete (status={status}).")

        # 5) Read thread messages and return the latest assistant text
        r = sess.get(
            f"{base}/threads/{thread_id}/messages",
            params={"api-version": api_version},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        messages = data.get("data", data)  # some clients return raw list

        # Find the last assistant message
        for m in reversed(messages):
            if m.get("role") == "assistant":
                content = m.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "text":
                            t = item.get("text")
                            if isinstance(t, dict) and "value" in t:
                                return str(t["value"])
                            if isinstance(t, str):
                                return t
        return ""
    
    if MODE == "local_python":
        # Call a Python function in your repository directly (no HTTP, no Azure).
        # Set LOCAL_HANDLER like "agents.weather:run" (module_path:function_name).
        handler_spec = os.getenv("LOCAL_HANDLER", "agents.weather:run")

        # Ensure repo root is on sys.path so "agents.*" can be imported
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        try:
            module_path, func_name = handler_spec.split(":")
        except ValueError:
            raise RuntimeError(f"LOCAL_HANDLER must look like 'package.module:function', got {handler_spec!r}")

        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            raise RuntimeError(f"Could not import module {module_path!r}: {e}") from e

        fn = getattr(mod, func_name, None)
        if not callable(fn):
            raise RuntimeError(f"Function {func_name!r} not found/callable in module {module_path!r}")

        # Call your function. Expected signature: fn(prompt: str, context: str|None) -> str|dict
        result = fn(prompt, context)

        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for k in ("output", "response", "answer", "text"):
                if k in result:
                    return str(result[k])
            return json.dumps(result, ensure_ascii=False)
        return str(result)



    raise RuntimeError(f"Unknown AGENT_MODE={MODE}")

