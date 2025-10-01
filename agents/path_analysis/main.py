import os
import logging
import osmnx as ox
from typing import Any, Dict

from shared.a2a_envelope import wrap_envelope
from shared.redis_bus import RedisBus

from agents.path_analysis.dem_utils import *
from agents.path_analysis.osm_utils import *
from agents.path_analysis.pathing import * 
from agents.path_analysis.llm import * 

AGENT_NAME = os.getenv("AGENT_NAME", "path-analysis-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1.1")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

STREAM_NAME = "path.analysis.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

DEM_PATH = os.getenv("DEM_PATH", "agents/path_analysis/data/slo_dem.tif")
START_LON = float(os.getenv("START_LON", "-120.6605"))
START_LAT = float(os.getenv("START_LAT", "35.2980"))
TOP_K = int(os.getenv("TOP_K", "3"))

DO_VISUALIZE = os.getenv("DO_VISUALIZE", "true").lower() in {"1", "true", "yes"}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)

def compute_paths_payload() -> Dict[str, Any]:
    logger.info("Loading DEM...")
    elevation, transform, crs, bounds = load_dem(DEM_PATH)

    logger.info("Loading OSM graph from DEM bounds...")
    north, south, east, west = bounds_to_latlon_bounds(bounds, crs)
    G = load_osm_graph_from_bounds(north, south, east, west)
    G = ox.project_graph(G, to_crs=crs)

    logger.info("Computing slope from DEM...")
    slope = compute_slope_numpy(elevation, transform)

    logger.info("Adding elevation and slope data to graph...")
    ox.elevation.add_node_elevations_raster(G, filepath=DEM_PATH)
    ox.elevation.add_edge_grades(G, add_absolute=True)
    G = add_slope(G, slope, transform)

    logger.info("Adding Tobler hiking time and custom edge costs...")
    G = add_tobler_time(G)
    G = add_custom_edge_costs(G)

    logger.info("Tagging graph with SAR-relevant POIs...")
    G = add_pois_to_graph(G, crs, (west, south, east, north))

    logger.info("Planning paths from start (lon=%s, lat=%s)...", START_LON, START_LAT)
    paths = plan_paths_to_all_pois_from_latlon_with_edges(G, START_LON, START_LAT, crs)
    top_paths = sorted(paths, key=lambda x: x[3])[:TOP_K]

    logger.info("Extracting path metadata...")
    path_data = extract_paths_metadata(G, top_paths, crs)

    if DO_VISUALIZE:
        logger.info("Visualizing graph & terrain (DO_VISUALIZE=true)...")
        visualize_graph_with_array(
            G,
            raster_array=elevation,
            transform=transform,
            title="OSM Graph with Top SAR Paths",
            paths=top_paths,
        )

    logger.info("Summarizing top paths with LLM...")
    try:
        llm_summary = summarize_multiple_paths_with_llm(path_data)
    except Exception as e:
        logger.warning(f"LLM summary failed: {e}. Using fallback summary.")
        llm_summary = "Path analysis completed successfully. LLM summary unavailable due to API key issues."

    final_data = prepare_path_for_redis(path_data, llm_summary)

    payload = {
        "source": {
            "dem_path": DEM_PATH,
            "bounds_latlon": {"north": north, "south": south, "east": east, "west": west},
        },
        "start": {"lon": START_LON, "lat": START_LAT},
        "top_k": TOP_K,
        "results": final_data,
    }
    return payload

def run_and_publish_path_analysis(bus: RedisBus):
    try:
        payload = compute_paths_payload()

        message_to_publish = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=STREAM_NAME,
        )
        bus.publish(message_to_publish)
        logger.info("Published path-analysis results to stream: %s", STREAM_NAME)

    except Exception as e:
        logger.error(f"An unhandled error occurred: {e}", exc_info=True)
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": f"Failed while computing paths for DEM={DEM_PATH} start=({START_LON},{START_LAT})",
        }
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM,
        )
        bus.publish(error_message)

def main():
    logger.info(f"Initializing {AGENT_NAME}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logger.info("%s running once (no schedule).", AGENT_NAME)
    run_and_publish_path_analysis(bus)





if __name__ == "__main__":
    main()