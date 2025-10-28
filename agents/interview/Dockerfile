FROM python:3.10-slim

# Set working directory
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pipx and poetry
RUN apt-get update && apt-get install -y pipx && pipx install poetry
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY poetry.lock pyproject.toml ./
COPY .env ./
COPY agents/interview/main.py ./agents/interview/

# Install Python dependencies
# RUN poetry install --no-dev

# Set environment variables
ENV AGENT_NAME=interview-agent
ENV AGENT_VERSION=1.0
ENV REDIS_URL=redis://redis:6379

CMD ["sleep", "infinity"]