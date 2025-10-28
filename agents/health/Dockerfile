FROM python:3.10-slim

# Set working directory
WORKDIR /workspace

# Install pipx and poetry
RUN apt-get update && apt-get install -y pipx && pipx install poetry
ENV PATH="/root/.local/bin:$PATH"
RUN poetry --version

# Copy project files
COPY poetry.lock pyproject.toml ./
COPY .env ./
COPY agents/health/main.py ./agents/health/

# Set environment variables
ENV AGENT_NAME=health-agent
ENV AGENT_VERSION=1.0
ENV REDIS_URL=redis://redis:6379

CMD ["sleep", "infinity"]
