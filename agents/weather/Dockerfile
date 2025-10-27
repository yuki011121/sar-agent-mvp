FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install only the dependencies that weather agent needs
RUN pip install --no-cache-dir \
    requests \
    redis \
    python-dotenv

# Install shared package from GitHub directly
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/weather ./agents/weather
COPY agents/base_agent.py ./agents/base_agent.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379

WORKDIR /workspace/agents/weather

CMD ["python", "main.py"]