import heapq
import numpy as np
from rasterio.transform import rowcol, xy
from pyproj import Transformer

# Convert geographic coordinates (lat, lon) to raster pixel coordinates (row, col)
def latlon_to_pixel(lat, lon, transform, dem_crs):
    transformer = Transformer.from_crs("EPSG:4326", dem_crs, always_xy=True)
    x, y = transformer.transform(lon, lat)
    row, col = rowcol(transform, x, y)
    return row, col

# Convert raster pixel coordinates (row, col) to geographic coordinates (lat, lon)
def pixel_to_latlon(row, col, transform, crs):
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    x, y = xy(transform, row, col)
    lon, lat = transformer.transform(x, y)
    return lat, lon

# Check if a given (lat, lon) point lies within the bounds of the DEM (cost map)
def latlon_in_bounds(lat, lon, transform, crs, rows, cols):
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = transformer.transform(lon, lat)
    row, col = rowcol(transform, x, y)
    return (0 <= row < rows) and (0 <= col < cols)

# Calculate Octile distance heuristic between two points for pathfinding
def heuristic(a, b):
    D = 1
    D2 = np.sqrt(2)
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return D * (dx + dy) + (D2 - 2 * D) * min(dx, dy)

# Perform A* search on a cost map to find the lowest-cost path from start to goal given in lat/lon
def a_star(cost_map, start_latlon, goal_latlon, transform, crs):
    rows, cols = cost_map.shape
    if not latlon_in_bounds(*start_latlon, transform, crs, rows, cols):
        raise ValueError("Start location is outside the DEM bounds")
    if not latlon_in_bounds(*goal_latlon, transform, crs, rows, cols):
        raise ValueError("Goal location is outside the DEM bounds")
    
    start = latlon_to_pixel(*start_latlon, transform, crs)
    goal = latlon_to_pixel(*goal_latlon, transform, crs)

    rows, cols = cost_map.shape
    visited = set()
    came_from = {}
    g_score = {start: 0}

    open_set = []
    heapq.heappush(open_set, (heuristic(start, goal), 0, start))

    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                (-1, -1), (-1, 1), (1, -1), (1, 1)]

    while open_set:
        f, current_g, current = heapq.heappop(open_set)

        if current in visited:
            continue
        visited.add(current)

        if current == goal:
            path_px = [current]
            while current in came_from:
                current = came_from[current]
                path_px.append(current)
            path_px.reverse()

            path_latlon = [pixel_to_latlon(r, c, transform, crs) for r, c in path_px]
            return path_latlon

        for dx, dy in directions:
            neighbor = (current[0] + dx, current[1] + dy)
            if not (0 <= neighbor[0] < rows and 0 <= neighbor[1] < cols):
                continue
            if np.isinf(cost_map[neighbor]):
                continue  

            tentative_g = current_g + cost_map[neighbor]

            if neighbor not in g_score or tentative_g < g_score[neighbor]:
                g_score[neighbor] = tentative_g
                priority = tentative_g + heuristic(neighbor, goal)
                heapq.heappush(open_set, (priority, tentative_g, neighbor))
                came_from[neighbor] = current

    return None