import argparse
import osmnx as ox
from dem_utils import load_dem, compute_slope_numpy
from graph_utils import load_osm_graph_from_bounds, add_slope, add_tobler_time, add_behavior_costs, add_custom_edge_costs
from osm_utils import bounds_to_latlon_bounds, get_nearest_node_from_latlon
from simulation import run_monte_carlo
from probability_map import build_probability_geodataframe, export_geojson_for_caltopo, plot_probability_heatmap

def add_elevation_to_nodes(G, elevation_array, transform):
    from rasterio.transform import rowcol
    height, width = elevation_array.shape
    for node, data in G.nodes(data=True):
        try:
            x, y = data['x'], data['y']
            row, col = rowcol(transform, x, y)
            if 0 <= row < height and 0 <= col < width:
                elev = elevation_array[row, col]
                G.nodes[node]['elevation'] = float(elev)
            else:
                G.nodes[node]['elevation'] = 0.0
        except Exception:
            G.nodes[node]['elevation'] = 0.0
    return G

def main():
    parser = argparse.ArgumentParser(description="SAR Lost Person Simulation")
    parser.add_argument("--lat",     type=float, required=True,  help="LKP latitude")
    parser.add_argument("--lon",     type=float, required=True,  help="LKP longitude")
    parser.add_argument("--lpt",     type=str,   required=True,  help="Lost person type (e.g. hiker, child, dementia, despondent)")
    parser.add_argument("--dem",     type=str,   required=True,  help="Path to DEM .tif file")
    parser.add_argument("--runs",    type=int,   default=1000,   help="Number of Monte Carlo runs")
    parser.add_argument("--steps",   type=int,   default=200,    help="Max steps per simulation run")
    parser.add_argument("--output",  type=str,   default="probability_map.geojson", help="Output GeoJSON filename")
    args = parser.parse_args()

    # 1. Load DEM
    print("Loading DEM...")
    elevation, transform, crs, bounds = load_dem(args.dem)

    # 2. Compute slope
    print("Computing slope...")
    slope = compute_slope_numpy(elevation, transform)

    # 3. Build OSM graph from DEM bounds
    print("Loading OSM graph...")
    north, south, east, west = bounds_to_latlon_bounds(bounds, crs)
    G = load_osm_graph_from_bounds(north, south, east, west)


    # 4. Add terrain data to edges
    print("Adding terrain costs...")
    #there is an error in the slope being added
    G = add_slope(G, slope, transform, crs)
    G = add_custom_edge_costs(G)
    G = add_tobler_time(G)
    G = add_behavior_costs(G, args.lpt)


    # 5. Add elevation to nodes
    print("Adding elevation to nodes...")
    G = add_elevation_to_nodes(G, elevation, transform)

    # 6. Get LKP node
    print(f"Finding LKP node at ({args.lat}, {args.lon})...")
    lkp_node = get_nearest_node_from_latlon(G, args.lon, args.lat, crs)
    print(f"LKP snapped to node {lkp_node}")

    # 7. Run Monte Carlo simulation
    print(f"Running {args.runs} simulations for LPT: {args.lpt}...")
    results = run_monte_carlo(G, lkp_node, args.lpt, n_runs=args.runs, steps=args.steps)
    print(f"Simulations complete.")

    # 8. Build and export probability map
    print("Building probability map...")
    gdf = build_probability_geodataframe(G, results, crs)
    export_geojson_for_caltopo(gdf, args.output)
    print(f"Done. Output saved to: {args.output}")

    gdf = build_probability_geodataframe(G, results, crs)
    plot_probability_heatmap(gdf, args.lpt, output_path="heatmap.png")
    export_geojson_for_caltopo(gdf, args.output)
    return

if __name__ == "__main__":
    main()