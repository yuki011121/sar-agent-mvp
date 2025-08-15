import os
from dotenv import load_dotenv
import json
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("API_KEY")

if not api_key:
    raise ValueError("API_KEY not found. Make sure it's set in your .env file.")

genai.configure(api_key=api_key)

model = genai.GenerativeModel("gemini-1.5-flash")

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

def summarize_multiple_paths_with_llm(latlon_paths):
    summaries = []

    for i, path_data in enumerate(latlon_paths):
        path_data["path_id"] = i + 1
        metadata = summarize_path_metadata(path_data)
        summaries.append(metadata)

    prompt = f"""  
    You are a Search and Rescue (SAR) path analysis assistant.

    Below is structured data representing multiple potential SAR paths. Your job is to review this metadata and generate a concise summary **for each path**, returned as a numbered list in plain text.

    Each item in the list should describe one path and include:
    - POI name and type
    - Path distance and estimated time
    - Elevation gain and loss
    - Notable road or trail names (if any)
    - Terrain and surface conditions (surface type, highway type, slope)
    - Access limitations (e.g., private or restricted roads)
    - A difficulty rating from 1 (very easy) to 10 (very difficult), with a brief justification
    - A 2–3 sentence recommendation for SAR responders about suitability, risk, or priority
    - Whether the path seems likely for a missing person (based on slope, accessibility, etc.)

    Format your output as:
    1. <summary for Path 1>
    2. <summary for Path 2>
    ...

    Paths:
    {json.dumps(summaries, indent=2)}
    """

    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)

    # Split the response on numbered lines (e.g., "1. ", "2. ", etc.)
    import re
    split_summaries = re.split(r'\n\d+\.\s+', response.text.strip())

    # Remove empty entries and clean up
    return [s.strip() for s in split_summaries if s.strip()]


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

    # Handle both single and list inputs
    if isinstance(path_data, list) and isinstance(llm_summary, list):
        if len(path_data) != len(llm_summary):
            raise ValueError("Length of path_data and llm_summary must match")
        return [prepare_single(p, s) for p, s in zip(path_data, llm_summary)]
    elif isinstance(path_data, dict) and isinstance(llm_summary, str):
        return prepare_single(path_data, llm_summary)
    else:
        raise TypeError("Inputs must be (dict, str) or (list, list)")
