FROM python:3.10-slim

WORKDIR /workspace

# osmnx/geopandas need these
RUN apt-get update && apt-get install -y \
    libgeos-dev \
    libproj-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    numpy \
    osmnx \
    networkx \
    geopandas \
    shapely \
    google-generativeai \
    redis \
    python-dotenv

# Install shared package
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

COPY agents/path_analysis ./agents/path_analysis
COPY agents/base_agent.py ./agents/base_agent.py

ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379
ENV GRAPH_RADIUS_KM=5.0
ENV N_SIMULATIONS=200
ENV TOP_N_RESULTS=30

WORKDIR /workspace/agents/path_analysis

CMD ["python", "main.py"]
