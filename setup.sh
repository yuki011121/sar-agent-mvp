#!/bin/bash

set -e

echo "Starting SAR Multi-Agent MVP Setup..."

echo "Checking for Docker and Poetry..."
if ! command -v docker &> /dev/null
then
    echo "Docker could not be found. Please install Docker Desktop and ensure it's running."
    exit 1
fi
if ! command -v poetry &> /dev/null
then
    echo "Poetry could not be found. Please install Poetry."
    exit 1
fi
echo "Core tools are present."

echo "Starting Docker services (Redis & MinIO) in the background..."
docker compose up -d
echo "Docker services started."

echo "Setting up Python environment and installing dependencies..."
poetry env use python3
poetry install
echo "Python dependencies installed."

echo "Setup complete! You can now run the agents."
echo "To run the weather agent, use the command:"
echo "poetry run python -m agents.weather"