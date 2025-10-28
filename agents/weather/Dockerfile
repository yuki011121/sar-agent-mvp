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
COPY agents/weather/main.py ./agents/weather/

# Set environment variables
ENV AGENT_NAME=weather-agent
ENV AGENT_VERSION=1.1
ENV REDIS_URL=redis://redis:6379
ENV LATITUDE=35.2828
ENV LONGITUDE=-120.6596
ENV UPDATE_INTERVAL_SECONDS=3600

CMD ["sleep", "infinity"]
