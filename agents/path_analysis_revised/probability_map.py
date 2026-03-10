import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Point
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

def build_probability_geodataframe(G, monte_carlo_results, crs):
    n_runs = monte_carlo_results["n_runs"]
    visit_counts = monte_carlo_results["node_visit_counts"]
    endpoint_counts = monte_carlo_results["endpoint_counts"]

    records = []
    for node_id, visits in visit_counts.items():
        x = G.nodes[node_id].get('x')
        y = G.nodes[node_id].get('y')
        if x is None or y is None:
            continue
        records.append({
            "node_id": node_id,
            "x": x,
            "y": y,
            "visit_prob": visits / n_runs,
            "endpoint_prob": endpoint_counts.get(node_id, 0) / n_runs,
            "elevation": G.nodes[node_id].get("elevation", None),
            "geometry": Point(x, y)
        })

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs=crs)
    return gdf


def export_geojson_for_caltopo(gdf, output_path="probability_map.geojson"):
    # CalTopo expects WGS84
    gdf_wgs = gdf.to_crs("EPSG:4326")
    gdf_wgs.to_file(output_path, driver="GeoJSON")
    print(f"Exported to {output_path} — import this into CalTopo as a layer")



def plot_probability_heatmap(gdf, lpt_type, output_path="heatmap.png"):
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # --- Left plot: Visit Probability ---
    ax1 = axes[0]
    gdf_sorted = gdf.sort_values("visit_prob")
    scatter1 = ax1.scatter(
        gdf_sorted.geometry.x,
        gdf_sorted.geometry.y,
        c=gdf_sorted["visit_prob"],
        cmap="hot",
        s=8,
        alpha=0.8,
        norm=mcolors.PowerNorm(gamma=0.4)  # enhances contrast for low values
    )
    plt.colorbar(scatter1, ax=ax1, label="Visit Probability")
    ax1.set_title(f"Visit Density — {lpt_type.capitalize()}")
    ax1.set_xlabel("Longitude")
    ax1.set_ylabel("Latitude")

    # --- Right plot: Endpoint Probability ---
    ax2 = axes[1]
    gdf_sorted2 = gdf.sort_values("endpoint_prob")
    scatter2 = ax2.scatter(
        gdf_sorted2.geometry.x,
        gdf_sorted2.geometry.y,
        c=gdf_sorted2["endpoint_prob"],
        cmap="hot",
        s=8,
        alpha=0.8,
        norm=mcolors.PowerNorm(gamma=0.4)
    )
    plt.colorbar(scatter2, ax=ax2, label="Endpoint Probability")
    ax2.set_title(f"Endpoint Probability — {lpt_type.capitalize()}")
    ax2.set_xlabel("Longitude")
    ax2.set_ylabel("Latitude")

    # Mark the highest endpoint probability node
    max_idx = gdf["endpoint_prob"].idxmax()
    max_node = gdf.loc[max_idx]
    ax2.scatter(
        max_node.geometry.x,
        max_node.geometry.y,
        c="cyan", s=60, zorder=5, label=f"Highest probability"
    )
    ax2.legend()

    plt.suptitle(f"SAR Lost Person Simulation — {lpt_type.capitalize()}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Heatmap saved to: {output_path}")