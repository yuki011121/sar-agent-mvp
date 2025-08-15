import osmnx as ox
import matplotlib.pyplot as plt
import numpy as np
from rasterio.transform import rowcol
from rasterio.plot import show
import pandas as pd
from pyproj import Transformer

# Download walkable OSM graph using bounding box (based on DEM bounds)
def load_osm_graph_from_bounds(north, south, east, west, network_type='all'):
    ox.settings.useful_tags_node = [
    "highway", "barrier", "crossing", "amenity", "natural"
    ]

    ox.settings.useful_tags_way = [
        "highway", "name", "surface", "smoothness", "access", "width",
        "incline", "sac_scale", "trail_visibility", "tracktype", "bridge", "tunnel"
    ]
    bbox = (west, south, east, north)
    G = ox.graph_from_bbox(
        bbox,
        network_type=network_type,
        retain_all=True,
        truncate_by_edge=False,
        simplify=True,
        custom_filter=None
    )
    return G

# Add average slope (in degrees) to each edge using DEM slope raster
def add_slope(G, slope_array, transform):
    height, width = slope_array.shape

    for u, v, k, data in G.edges(keys=True, data=True):
        try:
            x1, y1 = G.nodes[u]['x'], G.nodes[u]['y']
            x2, y2 = G.nodes[v]['x'], G.nodes[v]['y']

            row1, col1 = rowcol(transform, x1, y1)
            row2, col2 = rowcol(transform, x2, y2)

            if all(0 <= r < height and 0 <= c < width for r, c in [(row1, col1), (row2, col2)]):
                slope1 = slope_array[row1, col1]
                slope2 = slope_array[row2, col2]
                avg_slope = np.mean([slope1, slope2])
                data["slope_deg"] = float(avg_slope)
        except Exception:
            continue

    return G

# Add Tobler's hiking time estimate (in minutes) to each edge based on slope and length
def add_tobler_time(G):
    for u, v, k, data in G.edges(keys=True, data=True):
        slope = data.get("grade", 0.0)  # or use slope_deg if that's more accurate
        length_m = data.get("length", 0)
        # Tobler's hiking speed in m/min
        speed = 6 * np.exp(-3.5 * abs(slope + 0.05)) * 1000 / 60
        time_min = length_m / speed if speed > 0 else 9999
        data["time_min"] = time_min
    return G

# Add a composite "cost" to each edge using length and slope
def add_custom_edge_costs(G):
    for u, v, k, data in G.edges(keys=True, data=True):
        length = data.get("length", 1.0)
        slope = data.get("slope_deg", 0.0)
        grade = data.get("grade_abs", 0.0)

        # Sanitize slope
        if not isinstance(slope, (int, float)) or slope != slope:  # slope != slope is NaN check
            slope = 0.0
        else:
            slope = abs(slope)

        # Sanitize grade
        if not isinstance(grade, (int, float)) or grade != grade:
            grade = 0.0

        # Compute cost safely
        cost = length * (1 + 0.1 * grade + 0.05 * slope)
        cost = max(0.001, cost)  # Clamp to avoid zero or negative costs

        data["cost"] = float(cost)

    return G

# Query SAR-relevant POIs and attach them to the nearest graph nodes with metadata
def add_pois_to_graph(G, crs, bounds):
    poi_tags = {
        'tourism': ['camp_site', 'viewpoint'],
        'amenity': ['shelter', 'ranger_station', 'emergency_phone'],
        'natural': ['peak', 'spring', 'cave_entrance'],
        'building': ['hut', 'cabin'],
        'highway': ['trailhead'],
        'place': ['isolated_dwelling', 'hamlet'],
        'emergency': ['phone', 'defibrillator'],
    }

    west, south, east, north = bounds
    bbox = (west, south, east, north)

    pois_gdf = ox.features.features_from_bbox(bbox=bbox, tags=poi_tags)

    tag_cols = [tag for tag in poi_tags.keys() if tag in pois_gdf.columns]
    filtered_pois = pois_gdf.dropna(subset=tag_cols, how='all').copy()

    def get_type(row):
        for tag in tag_cols:
            if pd.notna(row.get(tag)):
                return f"{tag}={row[tag]}"
        return "unknown"

    filtered_pois['type'] = filtered_pois.apply(get_type, axis=1)
    filtered_pois['name'] = filtered_pois['name'].fillna('[Unnamed]')
    filtered_pois = filtered_pois.to_crs(crs)

    for _, poi in filtered_pois.iterrows():
        geom = poi.geometry
        if geom.geom_type in ['Polygon', 'MultiPolygon']:
            point = geom.centroid
        elif geom.geom_type == 'Point':
            point = geom
        else:
            continue

        nearest_node = ox.distance.nearest_nodes(G, X=point.x, Y=point.y)
        G.nodes[nearest_node]['is_poi'] = True
        G.nodes[nearest_node]['poi_name'] = poi['name']
        G.nodes[nearest_node]['poi_type'] = poi['type']

    return G

def get_edge_with_min_weight(G, u, v, weight="cost"):
    best_k = None
    best_val = float("inf")
    for k, data in G[u][v].items():
        val = data.get(weight, float("inf"))
        if val < best_val:
            best_val = val
            best_k = k
    return G[u][v][best_k]

def visualize_graph_with_array(
    G,
    raster_array,
    transform,
    figsize=(10, 8),
    title=None,
    paths=None  # Optional: list of (poi_node, path, cost)
):
    fig, ax = plt.subplots(figsize=figsize)

    # Plot DEM raster
    show(raster_array, transform=transform, ax=ax, cmap='terrain')

    # Plot the base graph
    ox.plot_graph(
        G,
        ax=ax,
        node_color='black',
        node_size=5,
        edge_color='blue',
        edge_linewidth=1,
        bgcolor=None,
        show=False,
        close=False
    )

    # Plot POIs in red
    poi_nodes = [n for n, d in G.nodes(data=True) if d.get('is_poi')]
    x = [G.nodes[n]['x'] for n in poi_nodes]
    y = [G.nodes[n]['y'] for n in poi_nodes]
    ax.scatter(x, y, c='red', s=5, label='POI Nodes', zorder=2)

    # Plot paths if provided
    if paths:
        for i, (poi_node, path, edge_list, cost) in enumerate(paths):
            for u, v, k, edge in edge_list:
                if 'geometry' in edge:
                    xs, ys = edge['geometry'].xy
                else:
                    xs = [G.nodes[u]['x'], G.nodes[v]['x']]
                    ys = [G.nodes[u]['y'], G.nodes[v]['y']]
                ax.plot(xs, ys, color='orange', linewidth=1.5, zorder=1)

            # Mark the start node of the path
            start_node = path[0]
            ax.scatter(
                G.nodes[start_node]['x'],
                G.nodes[start_node]['y'],
                c='lime',
                s=5,
                label=f'Start {i+1}' if i == 0 else "",
                zorder=4
            )

            # Label the endpoint POI
            raw_name = G.nodes[poi_node].get('poi_name')
            poi_type = G.nodes[poi_node].get('poi_type', f'POI {i+1}')
            poi_name = raw_name if raw_name and raw_name != "[Unnamed]" else poi_type
            ax.text(
                G.nodes[poi_node]['x'],
                G.nodes[poi_node]['y'],
                f"{poi_name}",
                fontsize=8,
                color='darkred',
                zorder=3,
                ha='left',
                va='bottom'
            )

    if title:
        ax.set_title(title)
    ax.legend()
    plt.show()


def extract_paths_metadata(G, path_tuples, crs):
    transformer = Transformer.from_crs(crs.to_string(), "EPSG:4326", always_xy=True)
    results = []

    for poi_node, path, edges, cost in path_tuples:
        node_info = []
        latlon_path = []

        for n in path:
            node_data = dict(G.nodes[n])
            node_data["node"] = n
            lon, lat = transformer.transform(node_data["x"], node_data["y"])
            node_data["lat"] = lat
            node_data["lon"] = lon
            latlon_path.append((lat, lon))
            node_info.append(node_data)

        edge_info = []
        for u, v, k, data in edges:
            edge_data = dict(data)
            edge_data["from_node"] = u
            edge_data["to_node"] = v
            edge_data["key"] = k
            edge_info.append(edge_data)

        results.append({
            "poi_node": poi_node,
            "poi_name": G.nodes[poi_node].get("poi_name", "[Unnamed]"),
            "poi_type": G.nodes[poi_node].get("poi_type", "unknown"),
            "total_cost": cost,
            "path_latlon": [(n["lat"], n["lon"]) for n in node_info],
            "path_nodes": node_info,
            "path_edges": edge_info
        })

    return results
