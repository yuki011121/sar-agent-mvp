FROM python:3.10-slim

# Install system dependencies for OpenCV and image processing
# RUN apt-get update && apt-get install -y \
#     libglib2.0-0 \
#     libsm6 \
#     libxext6 \
#     libxrender-dev \
#     libgomp1 \
#     libglib2.0-0 \
#     libgthread-2.0-0 \
#     libgtk-3-0 \
#     libavcodec-dev \
#     libavformat-dev \
#     libswscale-dev \
#     libv4l-dev \
#     libxvidcore-dev \
#     libx264-dev \
#     libjpeg-dev \
#     libpng-dev \
#     libtiff-dev \
#     libatlas-base-dev \
#     python3-dev \
#     python3-numpy \
#     libtbb2 \
#     libtbb-dev \
#     libdc1394-22-dev \
#     && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install pipx and poetry
RUN apt-get update && apt-get install -y pipx && pipx install poetry
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY poetry.lock pyproject.toml ./
COPY .env ./
COPY agents/photo_analysis/main.py ./agents/photo_analysis/

# Install Python dependencies
# RUN poetry install --no-dev

# Pre-download YOLO model to avoid download during runtime
# RUN python -c "from ultralytics import YOLO; YOLO('yolov8m.pt')"

# Create input directory for images
RUN mkdir -p input_images

# Set environment variables
ENV IMAGE_INPUT_DIR=/workspace/input_images
ENV YOLO_MODEL_PATH=yolov8m.pt

CMD ["sleep", "infinity"]

