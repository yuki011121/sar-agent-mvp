import os
import time
import logging
import threading
import osmnx as ox
from typing import Any, Dict, Optional, Tuple, List

from shared import wrap_envelope, RedisBus

from agents.path_analysis.dem_utils import *
from agents.path_analysis.osm_utils import *
from agents.path_analysis.pathing import * 
from agents.path_analysis.llm import * 

AGENT_NAME = os.getenv("AGENT_NAME", "path-analysis-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "1.2")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

STREAM_NAME = "path.analysis.raw"
QUERY_INPUT_STREAM = "path.query.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

DEM_PATH = os.getenv("DEM_PATH", "agents/path_analysis/data/slo_dem.tif")
START_LON = float(os.getenv("START_LON", "-120.6605"))
START_LAT = float(os.getenv("START_LAT", "35.2980"))
TOP_K = int(os.getenv("TOP_K", "3"))

DO_VISUALIZE = os.getenv("DO_VISUALIZE", "true").lower() in {"1", "true", "yes"}
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 3600))  # Default: 1 hour
ENABLE_PERIODIC = os.getenv("ENABLE_PERIODIC", "false").lower() in {"1", "true", "yes"}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)

# Cached graph data to avoid reloading for every query
_cached_graph_data: Optional[Dict[str, Any]] = None
_cache_lock = threading.Lock()


def load_graph_data() -> Dict[str, Any]:
    """Load and cache graph data for path computation."""
    global _cached_graph_data
    
    with _cache_lock:
        if _cached_graph_data is not None:
            logger.info("Using cached graph data")
            return _cached_graph_data
        
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
        
        _cached_graph_data = {
            "G": G,
            "elevation": elevation,
            "transform": transform,
            "crs": crs,
            "bounds": {"north": north, "south": south, "east": east, "west": west}
        }
        
        logger.info("Graph data loaded and cached")
        return _cached_graph_data


def compute_paths_payload(start_lon: Optional[float] = None, 
                          start_lat: Optional[float] = None,
                          end_lon: Optional[float] = None,
                          end_lat: Optional[float] = None,
                          top_k: Optional[int] = None) -> Dict[str, Any]:
    """Compute paths with optional custom start/end points."""
    
    use_start_lon = start_lon if start_lon is not None else START_LON
    use_start_lat = start_lat if start_lat is not None else START_LAT
    use_top_k = top_k if top_k is not None else TOP_K
    
    # Load graph data (uses cache if available)
    graph_data = load_graph_data()
    G = graph_data["G"]
    elevation = graph_data["elevation"]
    transform = graph_data["transform"]
    crs = graph_data["crs"]
    bounds = graph_data["bounds"]

    logger.info(f"Planning paths from start (lon={use_start_lon}, lat={use_start_lat})...")
    
    if end_lon is not None and end_lat is not None:
        # Single path to specific destination
        # TODO: Implement single destination path computation
        logger.warning("Specific end point not yet supported, using POI-based routing")
    
    paths = plan_paths_to_all_pois_from_latlon_with_edges(G, use_start_lon, use_start_lat, crs)
    top_paths = sorted(paths, key=lambda x: x[3])[:use_top_k]

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
            "bounds_latlon": bounds,
        },
        "start": {"lon": use_start_lon, "lat": use_start_lat},
        "top_k": use_top_k,
        "results": final_data,
    }
    return payload


def run_and_publish_path_analysis(bus: RedisBus, task_id: Optional[str] = None,
                                   start_lon: Optional[float] = None,
                                   start_lat: Optional[float] = None,
                                   end_lon: Optional[float] = None,
                                   end_lat: Optional[float] = None,
                                   top_k: Optional[int] = None):
    """Run path analysis and publish results."""
    try:
        payload = compute_paths_payload(
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=end_lon,
            end_lat=end_lat,
            top_k=top_k
        )
        
        # Include task_id for correlation
        if task_id:
            payload["task_id"] = task_id

        message_to_publish = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=STREAM_NAME,
        )
        bus.publish(message_to_publish)
        logger.info(f"Published path-analysis results to stream: {STREAM_NAME}" +
                   (f" (task_id: {task_id})" if task_id else ""))

    except Exception as e:
        logger.error(f"An unhandled error occurred: {e}", exc_info=True)
        error_payload = {
            "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "context": f"Failed while computing paths for DEM={DEM_PATH}",
        }
        if task_id:
            error_payload["task_id"] = task_id
            
        error_message = wrap_envelope(
            payload=error_payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=DEAD_LETTER_STREAM,
        )
        bus.publish(error_message)


def periodic_publisher(bus: RedisBus):
    """Background thread for periodic path analysis (if enabled)."""
    logger.info(f"Periodic publisher started. Interval: {UPDATE_INTERVAL_SECONDS}s")
    while True:
        logger.info("Starting periodic path analysis cycle.")
        run_and_publish_path_analysis(bus)
        logger.info(f"Cycle complete. Sleeping for {UPDATE_INTERVAL_SECONDS} seconds...")
        time.sleep(UPDATE_INTERVAL_SECONDS)


def query_listener(bus: RedisBus):
    """Listen for on-demand path analysis queries via path.query.raw stream."""
    logger.info(f"Query listener started. Listening on: {QUERY_INPUT_STREAM}")
    
    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-query-group",
            consumer_name=f"{AGENT_NAME}-query-consumer",
            streams=[QUERY_INPUT_STREAM],
            block_ms=5000
        ):
            try:
                payload = message.payload
                logger.info(f"Received path analysis query: {payload}")
                
                # Extract parameters
                task_id = payload.get("task_id")
                
                # Support both array format [lat, lon] and separate fields
                start = payload.get("start")
                end = payload.get("end")
                
                start_lat = start_lon = end_lat = end_lon = None
                
                if start:
                    if isinstance(start, list) and len(start) == 2:
                        start_lat, start_lon = start
                    elif isinstance(start, dict):
                        start_lat = start.get("lat")
                        start_lon = start.get("lon")
                
                if end:
                    if isinstance(end, list) and len(end) == 2:
                        end_lat, end_lon = end
                    elif isinstance(end, dict):
                        end_lat = end.get("lat")
                        end_lon = end.get("lon")
                
                # Also check direct lat/lon fields
                if start_lat is None:
                    start_lat = payload.get("start_lat")
                if start_lon is None:
                    start_lon = payload.get("start_lon")
                    
                top_k = payload.get("top_k")
                
                # Convert to float if provided
                if start_lat is not None:
                    start_lat = float(start_lat)
                if start_lon is not None:
                    start_lon = float(start_lon)
                if end_lat is not None:
                    end_lat = float(end_lat)
                if end_lon is not None:
                    end_lon = float(end_lon)
                if top_k is not None:
                    top_k = int(top_k)
                
                # Process the query
                run_and_publish_path_analysis(
                    bus, 
                    task_id=task_id,
                    start_lon=start_lon,
                    start_lat=start_lat,
                    end_lon=end_lon,
                    end_lat=end_lat,
                    top_k=top_k
                )
                
            except Exception as e:
                logger.error(f"Error processing query message: {e}")
                
    except Exception as e:
        logger.error(f"Query listener error: {e}")


def main():
    logger.info(f"Initializing {AGENT_NAME} v{AGENT_VERSION}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logger.info(f"{AGENT_NAME} starting up.")
    
    # Pre-load graph data on startup (expensive operation)
    logger.info("Pre-loading graph data...")
    try:
        load_graph_data()
    except Exception as e:
        logger.error(f"Failed to pre-load graph data: {e}")
    
    # Start periodic publisher in background thread (if enabled)
    if ENABLE_PERIODIC:
        periodic_thread = threading.Thread(target=periodic_publisher, args=(bus,), daemon=True)
        periodic_thread.start()
    else:
        logger.info("Periodic publishing disabled. Running initial analysis...")
        run_and_publish_path_analysis(bus)
    
    # Run query listener in main thread
    query_listener(bus)


if __name__ == "__main__":
    main()