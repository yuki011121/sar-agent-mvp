FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    "pyautogen<0.3" \
    openai>=1.0.0 \
    redis>=6.0.0 \
    python-dotenv>=1.0.0

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code
COPY agents/command_agent ./agents/command_agent
COPY agents/base_agent.py ./agents/base_agent.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379

WORKDIR /workspace

CMD ["python", "agents/command_agent/main.py"]

