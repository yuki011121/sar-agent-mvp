import rasterio
import numpy as np
import matplotlib.pyplot as plt
#import richdem as rd  # Optional: Uncomment if using richdem-based slope

# Load elevation data from a DEM file
def load_dem(dem_path):
    with rasterio.open(dem_path) as src:
        elevation = src.read(1).astype(float)
        nodata = src.nodata
        transform = src.transform
        crs = src.crs
        if nodata is not None:
            elevation = np.ma.masked_equal(elevation, nodata)
    return elevation, transform, crs

# Compute slope from elevation using numpy gradient
def compute_slope_numpy(elevation, transform):
    x_res = transform.a  
    y_res = -transform.e 

    if np.ma.is_masked(elevation):
        elevation = elevation.filled(np.nan)

    dz_dy, dz_dx = np.gradient(elevation, y_res, x_res)

    grad_mag_squared = dz_dx**2 + dz_dy**2
    grad_mag_squared = np.nan_to_num(grad_mag_squared, nan=0.0)

    slope_rad = np.arctan(np.sqrt(grad_mag_squared))
    slope_deg = np.degrees(slope_rad)

    return slope_deg

# (Optional) Use richdem for more accurate slope, requires more memory
def compute_slope_rd(dem_path):
    elevation = load_dem(dem_path)
    dem_rd = rd.rdarray(elevation, no_data=np.nan)
    dem_rd.geotransform = [0, 1, 0, 0, 0, -1]
    slope_deg = rd.TerrainAttribute(dem_rd, attrib='slope_degrees')
    return slope_deg

# Convert slope to a cost map using Tobler's Hiking Function
def slope_to_cost_map(slope_deg):
    slope_rad = np.deg2rad(slope_deg)
    speed = 6 * np.exp(-3.5 * np.abs(np.tan(slope_rad) + 0.05))
    cost_map = 1 / (speed + 1e-6)  
    cost_map = np.clip(cost_map, None, 10)  
    cost_map[slope_deg > 30] = np.inf
    return cost_map

# Plot a 2D array with optional path overlay
def plot_array(arr, title, bar_title, path_px = None, cmap='terrain'):
    plt.figure(figsize=(8,6))
    plt.imshow(arr, cmap=cmap)
    plt.colorbar(label=bar_title)
    plt.title(title)
    if path_px is not None and len(path_px) > 1:
        y, x = zip(*path_px)
        plt.plot(x, y, color='black')
        plt.scatter([x[0], x[-1]], [y[0], y[-1]], color='red', label='Start/Goal', zorder=3)
        plt.legend()
    plt.tight_layout()
    plt.show()

