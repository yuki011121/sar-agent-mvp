import osmnx as ox
import geopandas as gpd
from shapely.geometry import Point
import pyproj
from pyproj import Transformer
import networkx as nx

# Convert DEM bounds (in projected CRS) to lat/lon bounding box
def bounds_to_latlon_bounds(bounds, dem_crs):
    transformer = Transformer.from_crs(dem_crs, "EPSG:4326", always_xy=True)
    west, south = transformer.transform(bounds.left, bounds.bottom)
    east, north = transformer.transform(bounds.right, bounds.top)
    return north, south, east, west

def get_nearest_node_from_latlon(G, lon, lat, crs):

    # Create a GeoSeries and project it
    point = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(crs)
    x, y = point.geometry.iloc[0].x, point.geometry.iloc[0].y

    # Find nearest node in projected graph
    nearest_node = ox.distance.nearest_nodes(G, X=x, Y=y)
    return nearest_node

def plan_paths_to_all_pois_from_latlon_with_edges(G, lon, lat, crs, weight="cost"):
    source_node = get_nearest_node_from_latlon(G, lon, lat, crs)
    poi_nodes = [n for n, d in G.nodes(data=True) if d.get("is_poi")]

    results = []
    for poi_node in poi_nodes:
        try:
            path = nx.shortest_path(G, source=source_node, target=poi_node, weight=weight)
            edges = []
            total_cost = 0.0
            for u, v in zip(path[:-1], path[1:]):
                best_k = min(
                    G[u][v].keys(),
                    key=lambda k: G[u][v][k].get(weight, float("inf"))
                )
                edge_data = G[u][v][best_k]
                edges.append((u, v, best_k, edge_data))
                total_cost += edge_data.get(weight, 0.0)
            results.append((poi_node, path, edges, total_cost))
        except nx.NetworkXNoPath:
            continue
    return results
