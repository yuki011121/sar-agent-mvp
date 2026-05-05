"""
Probability Map — Convert Monte Carlo results into structured output.

Produces a ranked list of (lat, lon, endpoint_probability, visit_density)
ready for Redis publish and frontend Leaflet heatmap rendering.
"""

import networkx as nx
from typing import Dict, List

from agents.path_analysis.simulation import MonteCarloResults


def build_probability_map(results: MonteCarloResults, graph: nx.Graph) -> Dict[int, Dict]:
    """
    Convert raw Monte Carlo counts into per-node probability scores.

    Returns dict: node_id -> {lat, lon, endpoint_probability, visit_density,
                               endpoint_count, visit_count}
    """
    total_runs = results.total_runs
    if total_runs == 0:
        return {}

    all_nodes = set(results.endpoint_counts.keys()) | set(results.visit_counts.keys())
    prob_map = {}

    for node in all_nodes:
        data = graph.nodes.get(node, {})
        lat = data.get("y", 0.0)
        lon = data.get("x", 0.0)

        ep_count = results.endpoint_counts.get(node, 0)
        visit_count = results.visit_counts.get(node, 0)

        prob_map[node] = {
            "lat": lat,
            "lon": lon,
            "endpoint_probability": ep_count / total_runs,
            "visit_density": visit_count / total_runs,
            "endpoint_count": ep_count,
            "visit_count": visit_count,
        }

    return prob_map


def get_top_points(prob_map: Dict[int, Dict], top_n: int = 30,
                   min_probability: float = 0.001) -> List[Dict]:
    """
    Return the top-N nodes by endpoint_probability as a sorted list of dicts,
    keeping absolute (not normalized) probabilities so values are comparable
    across queries.
    """
    filtered = [
        (node, data) for node, data in prob_map.items()
        if data["endpoint_probability"] >= min_probability
    ]
    filtered.sort(key=lambda x: x[1]["endpoint_probability"], reverse=True)

    results = []
    for rank, (node, data) in enumerate(filtered[:top_n], start=1):
        results.append({
            "lat": round(data["lat"], 6),
            "lon": round(data["lon"], 6),
            "endpoint_probability": round(data["endpoint_probability"], 4),
            "visit_density": round(data["visit_density"], 4),
            "endpoint_count": data["endpoint_count"],
            "rank": rank,
        })

    return results
