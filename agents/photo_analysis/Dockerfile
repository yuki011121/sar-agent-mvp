FROM python:3.10

WORKDIR /workspace

# Install system dependencies for image processing
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    ultralytics \
    opencv-python \
    pillow \
    numpy \
    redis \
    python-dotenv \
    requests \
    minio

# Install shared package from GitHub
RUN pip install --no-cache-dir git+https://github.com/RandomCyberCoder/Agentic-MVP-Shared.git

# Create models directory
RUN mkdir -p ./models

# Copy agent code
COPY agents/photo_analysis ./agents/photo_analysis
COPY agents/base_agent.py ./agents/base_agent.py
COPY agents/photo_analysis/models/yolov8m.pt ./models/yolov8m.pt

# Copy input images directory
COPY agents/photo_analysis/input_images ./input_images

# Set environment
ENV PYTHONPATH=/workspace
ENV REDIS_URL=redis://redis:6379
ENV YOLO_MODEL_PATH=/workspace/models/yolov8m.pt

WORKDIR /workspace

CMD ["python", "agents/photo_analysis/main.py"]