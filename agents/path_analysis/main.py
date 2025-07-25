import networkx as nx
from agents.path_analysis.dem_utils import *
from agents.path_analysis.osm_utils import *
from agents.path_analysis.pathing import * 

def main():
    print("Path Analysis Agent: Starting...")
    
    dem_path = "agents/path_analysis/data/slo_dem.tif"
    print("Loading DEM...")
    elevation, transform, crs, bounds = load_dem(dem_path)
    
    #OSM
    print("Loading OSM graph...")
    north, south, east, west = bounds_to_latlon_bounds(bounds, crs)
    G = load_osm_graph_from_bounds(north, south, east, west)
    G = ox.project_graph(G, to_crs=crs)

    #DEM
    print("Computing slope from DEM...")
    slope = compute_slope_numpy(elevation, transform)

    print("Adding elevation and slope data to graph...")
    ox.elevation.add_node_elevations_raster(G, filepath=dem_path)
    ox.elevation.add_edge_grades(G, add_absolute=True)
    G = add_slope(G, slope, transform)

    print("Adding Tobler hiking time and custom edge costs...")
    G = add_tobler_time(G)
    G = add_custom_edge_costs(G)

    print("Tagging graph nodes with SAR-relevant POIs...")
    G = add_pois_to_graph(G, crs, (west, south, east, north))

    print("Visualizing graph and terrain...")
    visualize_graph_with_array(
        G,
        raster_array=elevation,         
        transform=transform,           
        title='OSM Graph on DEM',
    )

    print("Path Analysis Agent: Done.")





if __name__ == "__main__":
    main()