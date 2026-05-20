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
    joblib \
    scikit-learn \
    fastapi \
    "uvicorn[standard]"

# Next two layers help install the sentence-transformers package (CPU version)
# Makes the image significantly smaller (by ~10GB)    
RUN pip install --no-cache-dir --timeout 300 --retries 5 torch \
    torchvision \
    torchaudio --index-url https://download.pytorch.org/whl/cpu

# sentence transformers installation to help avoid cuda download
RUN python -m pip install --no-cache-dir \
    --upgrade --upgrade-strategy only-if-needed \
    sentence-transformers

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