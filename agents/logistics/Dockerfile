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
COPY agents/logistics/main.py ./agents/logistics/
COPY agents/logistics/communications_agent.py ./agents/logistics/
COPY agents/logistics/logistics_chief.py ./agents/logistics/
COPY agents/logistics/resource_supply_agent.py ./agents/logistics/
COPY agents/logistics/transportation_agent.py ./agents/logistics/

# Set environment variables
ENV REDIS_URL=redis://redis:6379
ENV UPDATE_INTERVAL_SECONDS=1800

CMD ["sleep", "infinity"]
