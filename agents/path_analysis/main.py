from agents.path_analysis.dem_utils import *
from agents.path_analysis.pathing import * 
from rasterio.transform import xy
from pyproj import Transformer

def main():
    print("Path Analysis Agent: Starting...")

    dem_path = "agents/path_analysis/data/slo_dem.tif"

    print("Loading DEM...")
    elevation, transform, crs = load_dem(dem_path)
    #plot_array(elevation, "DEM", "Elevation (m)")

    print("Computing slope...")
    slope = compute_slope_numpy(elevation, transform)
    #slope = compute_slope_rd(elevation, transform)
    #plot_array(slope, "Slope Map", "Slope (degrees)")

    print("Converting slope to cost map...")
    cost_map = slope_to_cost_map(slope)
    #plot_array(cost_map, "Cost Map", "Cost")

    start = (35.20247994067715, -120.66029727164704)
    goal = (35.166441419294266, -120.66133051141357)
    print(f"Running A* from {start} (lat, lon) to {goal} (lat, lon)...")

    path = a_star(cost_map, start, goal, transform, crs)
    if path is None:
        print("No path found.")
        return

    path_pixels = [latlon_to_pixel(lat, lon, transform, crs) for lat, lon in path]
    #print(path_pixels)
    plot_array(cost_map, title="A* Path Over Cost Map", bar_title = "Cost", path_px=path_pixels)

    print("Path Analysis Agent: Done.")


if __name__ == "__main__":
    main()