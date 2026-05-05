import os
import logging
import osmnx as ox
from typing import Optional

from shared import wrap_envelope, RedisBus

from agents.path_analysis.classifier import classify_person, parse_person_info
from agents.path_analysis.simulation import run_monte_carlo, snap_to_graph
from agents.path_analysis.probability_map import build_probability_map, get_top_points
from agents.path_analysis.llm import summarize_results

AGENT_NAME = os.getenv("AGENT_NAME", "path-analysis-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "2.0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

STREAM_NAME = "path.analysis.raw"
QUERY_INPUT_STREAM = "path.query.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

GRAPH_RADIUS_KM = float(os.getenv("GRAPH_RADIUS_KM", "5.0"))
N_SIMULATIONS = int(os.getenv("N_SIMULATIONS", "200"))
TOP_N_RESULTS = int(os.getenv("TOP_N_RESULTS", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(AGENT_NAME)


def build_graph_from_lkp(lat: float, lon: float,
                          radius_km: float = GRAPH_RADIUS_KM) -> ox.graph:
    """Download OSM walk network centered on LKP, add elevation if available."""
    logger.info(f"Downloading OSM graph ({radius_km} km radius) for ({lat:.5f}, {lon:.5f})...")
    graph = ox.graph_from_point(
        (lat, lon),
        dist=radius_km * 1000,
        network_type="walk",
        simplify=True,
    )

    try:
        graph = ox.elevation.add_node_elevations_google(graph)
        logger.info("Elevation data added from Google.")
    except Exception:
        logger.info("Google elevation unavailable — using flat terrain.")
        for node in graph.nodes:
            graph.nodes[node]["elevation"] = 0.0

    # Add projected coordinates for distance calculations in simulation
    graph_proj = ox.project_graph(graph)
    for node in graph_proj.nodes:
        data = graph_proj.nodes[node]
        graph.nodes[node]["proj_x"] = data.get("x", 0)
        graph.nodes[node]["proj_y"] = data.get("y", 0)

    logger.info(f"Graph loaded: {graph.number_of_nodes()} nodes, "
                f"{graph.number_of_edges()} edges")
    return graph


def run_path_analysis(bus: RedisBus, task_id: Optional[str],
                      lat: float, lon: float,
                      age: int = 35,
                      cognitive_state: float = 0.9,
                      physical_condition: float = 0.8,
                      has_vehicle: bool = False,
                      radius_km: float = GRAPH_RADIUS_KM,
                      n_simulations: int = N_SIMULATIONS):
    try:
        # 1. Classify person → LPT profile
        person_class, profile = classify_person(
            age=age,
            cognitive_state=cognitive_state,
            physical_condition=physical_condition,
            has_vehicle=has_vehicle,
        )
        logger.info(f"Person classified as: {profile.name}")

        # 2. Download OSM graph on demand (any lat/lon)
        graph = build_graph_from_lkp(lat, lon, radius_km)

        # 3. Snap LKP to nearest graph node
        lkp_node = snap_to_graph(graph, lat, lon)
        logger.info(f"LKP snapped to node {lkp_node}")

        # 4. Monte Carlo simulation
        logger.info(f"Running {n_simulations} Monte Carlo simulations...")
        mc_results = run_monte_carlo(
            graph=graph,
            lkp_node=lkp_node,
            profile=profile,
            n_runs=n_simulations,
            verbose=False,
        )

        # 5. Build probability map
        prob_map = build_probability_map(mc_results, graph)
        top_points = get_top_points(prob_map, top_n=TOP_N_RESULTS)
        logger.info(f"Probability map built: {len(top_points)} high-probability points")

        # 6. LLM summary
        llm_summary = summarize_results(person_class, profile, top_points, lat, lon)

        payload = {
            "lkp": {"lat": lat, "lon": lon},
            "person_class": person_class,
            "person_profile": profile.name,
            "search_radius_km": {
                "p25": profile.search_radius_km[0],
                "p50": profile.search_radius_km[1],
                "p75": profile.search_radius_km[2],
                "p95": profile.search_radius_km[3],
            },
            "n_simulations": n_simulations,
            "probability_points": top_points,
            "summary": llm_summary,
        }
        if task_id:
            payload["task_id"] = task_id

        bus.publish(wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=STREAM_NAME,
        ))
        logger.info(f"Published results to {STREAM_NAME}"
                    + (f" (task_id: {task_id})" if task_id else ""))

    except Exception as e:
        logger.error(f"Path analysis failed: {e}", exc_info=True)
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
        }
        if task_id:
            error_payload["task_id"] = task_id

        bus.publish(wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM,
        ))


def query_listener(bus: RedisBus):
    logger.info(f"Query listener started on: {QUERY_INPUT_STREAM}")

    for message in bus.subscribe(
        group_name=f"{AGENT_NAME}-query-group",
        consumer_name=f"{AGENT_NAME}-query-consumer",
        streams=[QUERY_INPUT_STREAM],
        block_ms=5000,
    ):
        try:
            payload = message.payload
            logger.info(f"Received path analysis query: {payload}")

            task_id = payload.get("task_id")

            # Extract lat/lon — support both nested and flat formats
            start = payload.get("start") or {}
            if isinstance(start, list) and len(start) == 2:
                lat, lon = float(start[0]), float(start[1])
            elif isinstance(start, dict):
                lat = float(start.get("lat", 0))
                lon = float(start.get("lon", 0))
            else:
                lat = float(payload.get("start_lat", 0))
                lon = float(payload.get("start_lon", 0))

            if lat == 0 and lon == 0:
                logger.warning("Received path query with no valid coordinates, skipping.")
                continue

            # Extract person info
            person = parse_person_info(payload)

            radius_km = float(payload.get("radius_km", GRAPH_RADIUS_KM))
            n_simulations = int(payload.get("n_simulations", N_SIMULATIONS))

            run_path_analysis(
                bus=bus,
                task_id=task_id,
                lat=lat,
                lon=lon,
                age=person["age"],
                cognitive_state=person["cognitive_state"],
                physical_condition=person["physical_condition"],
                has_vehicle=person["has_vehicle"],
                radius_km=radius_km,
                n_simulations=n_simulations,
            )

        except Exception as e:
            logger.error(f"Error processing query message: {e}", exc_info=True)


def main():
    logger.info(f"Initializing {AGENT_NAME} v{AGENT_VERSION}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis: {e}")
        return

    logger.info("Ready. Waiting for queries on path.query.raw ...")
    query_listener(bus)


if __name__ == "__main__":
    main()
