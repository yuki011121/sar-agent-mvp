import os
from dotenv import load_dotenv
import json
import re
import google.generativeai as genai

from shared.mcp_tools import create_tool_use_request, get_tool_call_from_response

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY, GEMINI_API_KEY, or API_KEY not found. Make sure one is set in your .env file.")
genai.configure(api_key=api_key)

MODEL_NAME = os.getenv("GEN_TEXT_MODEL", "gemini-2.0-flash")
model = genai.GenerativeModel(MODEL_NAME)

# Summarize one path: IDs, cost/time, elevation stats, and unique OSM tags.
def summarize_path_metadata(path_data):
    def collect_unique(k, path_edges):
        return sorted(set(str(e[k]) for e in path_edges if e.get(k) is not None))

    node_elevations = [n.get("elevation") for n in path_data["path_nodes"] if n.get("elevation") is not None]
    edge_data = path_data["path_edges"]

    gain = sum(max(0, b - a) for a, b in zip(node_elevations[:-1], node_elevations[1:]))
    loss = sum(max(0, a - b) for a, b in zip(node_elevations[:-1], node_elevations[1:]))

    return {
        "path_id": path_data.get("path_id", "N/A"),
        "poi_node": path_data.get("poi_node", "N/A"),
        "poi_name": path_data.get("poi_name", "[Unnamed]"),
        "poi_type": path_data.get("poi_type", "unknown"),
        "total_cost": round(path_data["total_cost"], 2),
        "total_length_m": round(sum(e.get("length", 0) for e in edge_data), 2),
        "total_time_min": round(sum(e.get("time_min", 0) for e in edge_data), 2),
        "elevation_gain_m": round(gain, 2),
        "elevation_loss_m": round(loss, 2),
        "avg_slope_deg": round(sum(e.get("slope_deg", 0) for e in edge_data if e.get("slope_deg") is not None) / len(edge_data), 2) if edge_data else "N/A",
        "max_slope_deg": round(max(e.get("slope_deg", 0) for e in edge_data if e.get("slope_deg") is not None), 2) if edge_data else "N/A",
        "surface_types": collect_unique("surface", edge_data),
        "highway_types": collect_unique("highway", edge_data),
        "access_types": collect_unique("access", edge_data),
        "used_road_names": collect_unique("name", edge_data),
        "tracktypes": collect_unique("tracktype", edge_data),
        "sac_scales": collect_unique("sac_scale", edge_data),
        "trail_visibility": collect_unique("trail_visibility", edge_data),
        "inclines": collect_unique("incline", edge_data),
        "bridges": collect_unique("bridge", edge_data),
        "tunnels": collect_unique("tunnel", edge_data),
        "widths": collect_unique("width", edge_data)
    }

def _choose_summary_params_via_mcp(paths_metadata):
    tools = [{
        "type": "function",
        "function": {
            "name": "summarize_paths",
            "description": "Choose parameters for summarizing SAR paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "object"}},
                    "style": {"type": "string", "enum": ["brief", "detailed", "field-ops"]},
                    "audience": {"type": "string", "enum": ["dispatch", "field", "planning"]},
                },
                "required": ["paths"]
            },
        },
    }]

    req = create_tool_use_request(
        conversation=[{
            "role": "user",
            "content": (
                "Pick parameters (style, audience) to summarize these SAR paths. "
                "Default to style='field-ops' and audience='field' if unsure.\n\n"
                f"Paths JSON:\n{json.dumps(paths_metadata)[:12000]}"  
            ),
        }],
        tools=tools,
        system_instruction="You are a SAR planner. Select exactly one tool with JSON args.",
        provider="gemini",
        model=MODEL_NAME,  
    )

    resp = model.generate_content(
        req["contents"],
        tools=req["tools"],
        tool_config={"function_calling_config": {"mode": "AUTO"}},
    )

    resp_dict = resp.to_dict()
    parsed = get_tool_call_from_response(resp_dict, provider="gemini")

    if not parsed:
        return {"paths": paths_metadata, "style": "field-ops", "audience": "field"}

    tool_name, tool_args = parsed
    if tool_name != "summarize_paths" or not isinstance(tool_args, dict):
        return {"paths": paths_metadata, "style": "field-ops", "audience": "field"}

    return {
        "paths": tool_args.get("paths", paths_metadata),
        "style": tool_args.get("style", "field-ops"),
        "audience": tool_args.get("audience", "field"),
    }

# Produce concise field-ops summaries per path using MCP-chosen style/audience (returns list[str]).
def summarize_multiple_paths_with_llm(latlon_paths):
    meta = []
    for i, path_data in enumerate(latlon_paths):
        path_data["path_id"] = i + 1
        meta.append(summarize_path_metadata(path_data))

    params = _choose_summary_params_via_mcp(meta)
    style = params["style"]
    audience = params["audience"]
    paths_for_summary = params["paths"]

    prompt = f"""You are a Search and Rescue (SAR) path analysis assistant.

Audience: {audience}
Style preset: {style}

Using the path metadata below, write a short field-ops description for EACH path:
- Start with: POI: <name> (<type>). If missing, write POI: [Unnamed] (unknown).
- Describe the likely route in natural language, citing proper nouns (roads, trails, landmarks) where helpful.
- Difficulty: <1–10> — add a brief qualitative reason (no raw numbers).
- SAR Recommendation: concise operational guidance (tactics, access/permission checks, hazards, team/equipment, or priority).

Rules: Do NOT restate numeric metrics (distance, time, elevation, slope). Avoid raw tag dumps; use plain English.

Format your output as:
1. <summary for Path 1>
2. <summary for Path 2>
...

Paths:
{json.dumps(paths_for_summary, indent=2)}
"""
    response = model.generate_content(prompt)

    text = (getattr(response, "text", None) or "").strip()
    split_summaries = re.split(r"\n\d+\.\s+", text)
    return [s.strip() for s in split_summaries if s.strip()]

# Convert path metadata + LLM summaries into Redis-ready dict(s): {poi, summary, metrics, features, path_latlon}.
def prepare_path_for_redis(path_data, llm_summary):
    def collect_unique(k, items):
        return sorted(set(str(i[k]) for i in items if i.get(k) is not None))

    def prepare_single(path, summary):
        path_id = path.get("path_id", "N/A")
        poi_node = path.get("poi_node", "N/A")
        poi_name = path.get("poi_name", "[Unnamed]")
        poi_type = path.get("poi_type", "unknown")

        poi_node_data = next((n for n in path["path_nodes"] if n.get("node") == poi_node), {})
        lat = poi_node_data.get("lat")
        lon = poi_node_data.get("lon")

        edge_data = path["path_edges"]
        node_elevations = [n.get("elevation") for n in path["path_nodes"] if n.get("elevation") is not None]

        gain = sum(max(0, b - a) for a, b in zip(node_elevations[:-1], node_elevations[1:]))
        loss = sum(max(0, a - b) for a, b in zip(node_elevations[:-1], node_elevations[1:]))

        total_length = round(sum(e.get("length", 0) for e in edge_data), 2)
        total_time = round(sum(e.get("time_min", 0) for e in edge_data), 2)
        total_cost = round(path.get("total_cost", 0.0), 2)
        avg_slope = round(sum(e.get("slope_deg", 0) for e in edge_data if e.get("slope_deg") is not None) / len(edge_data), 2) if edge_data else "N/A"
        max_slope = round(max(e.get("slope_deg", 0) for e in edge_data if e.get("slope_deg") is not None), 2) if edge_data else "N/A"

        return {
            "path_id": path_id,
            "poi": {
                "node": poi_node,
                "name": poi_name,
                "type": poi_type,
                "lat": lat,
                "lon": lon
            },
            "summary": summary,
            "metrics": {
                "total_cost": total_cost,
                "total_length_m": total_length,
                "total_time_min": total_time,
                "elevation_gain_m": round(gain, 2),
                "elevation_loss_m": round(loss, 2),
                "avg_slope_deg": avg_slope,
                "max_slope_deg": max_slope,
            },
            "features": {
                "highways": collect_unique("highway", edge_data),
                "access": collect_unique("access", edge_data),
                "surface": collect_unique("surface", edge_data),
                "roads": collect_unique("name", edge_data),
                "tracktype": collect_unique("tracktype", edge_data),
                "sac_scale": collect_unique("sac_scale", edge_data),
                "trail_visibility": collect_unique("trail_visibility", edge_data),
                "bridges": collect_unique("bridge", edge_data),
                "tunnels": collect_unique("tunnel", edge_data),
                "inclines": collect_unique("incline", edge_data),
                "widths": collect_unique("width", edge_data)
            },
            "path_latlon": [
                (n["lat"], n["lon"])
                for n in path["path_nodes"]
                if "lat" in n and "lon" in n
            ]
        }

    if isinstance(path_data, list) and isinstance(llm_summary, list):
        if len(path_data) != len(llm_summary):
            raise ValueError("Length of path_data and llm_summary must match")
        return [prepare_single(p, s) for p, s in zip(path_data, llm_summary)]
    elif isinstance(path_data, dict) and isinstance(llm_summary, str):
        return prepare_single(path_data, llm_summary)
    elif isinstance(path_data, list) and isinstance(llm_summary, str):
        # Handle case where we have multiple paths but single summary
        return [prepare_single(p, llm_summary) for p in path_data]
    else:
        raise TypeError(f"Inputs must be (dict, str), (list, list), or (list, str). Got ({type(path_data)}, {type(llm_summary)})")
