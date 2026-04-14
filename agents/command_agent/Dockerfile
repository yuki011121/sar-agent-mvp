FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies from requirements.txt
COPY agents/command_agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/command_agent ./agents/command_agent
COPY agents/base_agent.py ./agents/base_agent.py
COPY agents/__init__.py ./agents/__init__.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379

WORKDIR /workspace

CMD ["python", "-m", "agents.command_agent.main"]

