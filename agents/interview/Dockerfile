FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    requests \
    redis \
    python-dotenv \
    PyPDF2 \
    google-generativeai \
    fastapi \
    "uvicorn[standard]" \
    "transformers>=4.40"

# CPU-only torch — avoids pulling 1 GB of CUDA libraries (GPU not needed for BERT inference)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Copy agent code and security defenses
COPY agents/interview ./agents/interview
COPY agents/base_agent.py ./agents/base_agent.py
COPY security/defenses ./security/defenses
COPY security/__init__.py ./security/__init__.py

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379
ENV HF_HUB_DISABLE_XET=1

WORKDIR /workspace/agents/interview

CMD ["python", "main.py"]
