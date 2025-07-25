import rasterio
import numpy as np
from rasterio.windows import from_bounds
from pyproj import Transformer
#import richdem as rd  # Optional: Uncomment if using richdem-based slope

# Load elevation data from a DEM file
def load_dem(dem_path):
    with rasterio.open(dem_path) as src:
        elevation = src.read(1).astype(float)
        nodata = src.nodata
        transform = src.transform
        crs = src.crs
        bounds = src.bounds
        if nodata is not None:
            elevation = np.ma.masked_equal(elevation, nodata)
    return elevation, transform, crs, bounds

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