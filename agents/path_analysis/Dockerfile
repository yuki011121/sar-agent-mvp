FROM python:3.10-slim

# Set working directory
WORKDIR /workspace

# Install system dependencies for geospatial libraries and OSM
# RUN apt-get update && apt-get install -y \
#     build-essential \
#     cmake \
#     gdal-bin \
#     libgdal-dev \
#     python3-gdal \
#     libgeos-dev \
#     libproj-dev \
#     libspatialite-dev \
#     libsqlite3-dev \
#     libffi-dev \
#     libssl-dev \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Install pipx and poetry
RUN apt-get update && apt-get install -y pipx && pipx install poetry
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY poetry.lock pyproject.toml ./
COPY .env ./
COPY agents/path_analysis/main.py ./agents/path_analysis/
COPY agents/path_analysis/dem_utils.py ./agents/path_analysis/
COPY agents/path_analysis/osm_utils.py ./agents/path_analysis/
COPY agents/path_analysis/pathing.py ./agents/path_analysis/
COPY agents/path_analysis/llm.py ./agents/path_analysis/

# Install Python dependencies
# RUN poetry install --no-dev

# Set environment variables
ENV AGENT_NAME=path-analysis-agent
ENV AGENT_VERSION=1.1
ENV REDIS_URL=redis://redis:6379
ENV DEM_PATH=agents/path_analysis/data/slo_dem.tif
ENV START_LON=-120.6605
ENV START_LAT=35.2980
ENV TOP_K=3
ENV DO_VISUALIZE=false

CMD ["sleep", "infinity"]
