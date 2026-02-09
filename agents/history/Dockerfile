FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    google-genai \
    redis \
    python-dotenv \
    qdrant-client \
    sentence-transformers \
    joblib \
    scikit-learn

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code (this will copy everything including models directory)
COPY agents/history ./agents/history
COPY agents/base_agent.py ./agents/base_agent.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379
ENV QDRANT_URL=http://host.docker.internal:6333

WORKDIR /workspace/agents/history

CMD ["bash", "-c", "cd /workspace && python agents/history/main.py"]