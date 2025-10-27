FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    networkx \
    numpy \
    openai \
    redis \
    python-dotenv

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/cluemeister ./agents/cluemeister
COPY agents/base_agent.py ./agents/base_agent.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379

WORKDIR /workspace/agents/cluemeister

CMD ["python", "main.py"]