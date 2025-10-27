FROM python:3.10

WORKDIR /workspace

# Install system dependencies for GIS libraries (GDAL, etc.)
RUN apt-get update && apt-get install -y \
    git \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# Install Python dependencies
RUN pip install --no-cache-dir \
    numpy \
    rasterio \
    geopandas \
    pyproj \
    osmnx \
    networkx \
    shapely \
    fiona \
    matplotlib \
    scipy \
    google-generativeai \
    redis \
    python-dotenv

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/path_analysis ./agents/path_analysis
COPY agents/base_agent.py ./agents/base_agent.py

# Copy DEM data files
COPY agents/path_analysis/data ./agents/path_analysis/data/

# Ensure data directory exists and files are accessible
RUN ls -la /workspace/agents/path_analysis/data/

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379
ENV DEM_PATH=/workspace/agents/path_analysis/data/slo_dem.tif

WORKDIR /workspace/agents/path_analysis

CMD ["python", "main.py"]