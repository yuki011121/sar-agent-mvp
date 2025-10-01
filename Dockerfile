# Use Python 3.10 slim as base image
FROM python:3.10-slim

# Set working directory
WORKDIR /workspace

# Update package list and install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry~=1.8.0

# Configure Poetry to create virtual environment in project folder (.venv)
RUN poetry config virtualenvs.in-project true

# Copy dependency definition files
COPY pyproject.toml poetry.lock* ./

# Run poetry install to install all project dependencies
RUN poetry install --no-root --no-dev

# Copy all other project files
COPY . .

# Add Poetry virtual environment bin directory to system PATH
ENV PATH="/workspace/.venv/bin:$PATH"
ENV PYTHONPATH="/workspace:$PYTHONPATH"

# Keep container running
CMD ["sleep", "infinity"]