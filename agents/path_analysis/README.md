# Path Analysis Agent

## DEM Download Instructions

To run the pathfinding system, follow these steps to manually download a high-resolution DEM:

1. Visit the USGS National Map Downloader:  
   https://apps.nationalmap.gov/downloader/

2. In the Data panel on the left, expand:  
   Elevation Products (3D Elevation Program Products and Services)

   > You may select any DEM to download based on your area of interest.  
   > Note: Larger areas or higher-resolution DEMs may require more memory and processing time.  
   > For this example, continue with the following steps to use the same area used in development.

3. In the map panel on the right, search for:  
   San Luis Obispo

4. Check the box for:  
   1-meter DEM

5. Click Search Products, then locate the following DEM:

   - Name: USGS 1 Meter 10 x71y390 CA_AZ_FEMA_R9_Lidar_2017_D18
   - Published Date: 2021-06-19
   - Metadata Updated: 2021-06-21
   - Format: GeoTIFF
   - Extent: 10,000 x 10,000 meters

6. Click the Download link (TIF).

7. Rename the downloaded file to:  
   slo_dem.tif

8. Move the file to the following directory in your project:  
   agents/path_analysis/data/slo_dem.tif

9. Open your main script and verify or update the file path if it differs.

10. To run:
    poetry run python -m agents.path_analysis.main
