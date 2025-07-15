import os
import time
import logging
import json
import redis
from datetime import datetime
from ultralytics import YOLO
from PIL import Image

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
IMAGE_INPUT_DIR = os.getenv("IMAGE_INPUT_DIR", "input_images")
REDIS_OUTPUT_STREAM = os.getenv("REDIS_OUTPUT_STREAM", "photo.analysis.raw")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8s.pt")  # Change from yolov8n.pt
AGENT_VERSION = "photo-analysis-agent-v1.0"
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 10))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logging.info(f"Successfully connected to Redis at {REDIS_URL}")
except redis.exceptions.ConnectionError as e:
    logging.error(f"Could not connect to Redis: {e}")
    exit(1)

try:
    model = YOLO(YOLO_MODEL_PATH)
    logging.info(f"Loaded YOLOv8 model from {YOLO_MODEL_PATH}")
except Exception as e:
    logging.error(f"Failed to load YOLOv8 model: {e}")
    exit(1)

def analyze_image(image_path):
    try:
        results = model(image_path)
        detections = []
        for result in results:
            for box in result.boxes:
                detections.append({
                    "class": model.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "bbox": [float(x) for x in box.xyxy[0].tolist()]
                })
        return detections
    except Exception as e:
        logging.error(f"Error analyzing image {image_path}: {e}")
        return []

def publish_to_redis(message: dict):
    try:
        message_id = redis_client.xadd(REDIS_OUTPUT_STREAM, {"data": json.dumps(message)})
        logging.info(f"Published analysis to stream '{REDIS_OUTPUT_STREAM}' with ID {message_id}")
    except redis.exceptions.RedisError as e:
        logging.error(f"Failed to publish to Redis: {e}")

def main():
    logging.info(f"{AGENT_VERSION} starting up. Monitoring {IMAGE_INPUT_DIR} for new images.")
    processed_files = set()
    while True:
        try:
            files = [f for f in os.listdir(IMAGE_INPUT_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        except FileNotFoundError:
            os.makedirs(IMAGE_INPUT_DIR, exist_ok=True)
            files = []
        new_files = [f for f in files if f not in processed_files]
        for filename in new_files:
            image_path = os.path.join(IMAGE_INPUT_DIR, filename)
            logging.info(f"Analyzing image: {image_path}")
            detections = analyze_image(image_path)
            message = {
                "metadata": {
                    "agent_name": AGENT_VERSION,
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "source": "YOLOv8",
                    "image_file": filename
                },
                "detections": detections
            }
            # Print the full output to the console in a readable format
            print("\n=== Photo Analysis Output ===")
            print(json.dumps(message, indent=2))
            print("============================\n")
            publish_to_redis(message)
            processed_files.add(filename)
        time.sleep(UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main() 