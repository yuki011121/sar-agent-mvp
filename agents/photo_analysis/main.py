import os
import time
import logging
import json
import redis
import tempfile
import requests
from datetime import datetime
from ultralytics import YOLO
from PIL import Image
import cv2
import numpy as np
import traceback
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# Import RedisBus for StandardMessage format
from shared import RedisBus, wrap_envelope

# MinIO client for downloading images from object storage
try:
    from minio import Minio
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    logging.warning("minio not available. Install with: pip install minio")

# Additional imports for enhanced person analysis
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    logging.warning("face_recognition not available. Install with: pip install face-recognition")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
IMAGE_INPUT_DIR = os.getenv("IMAGE_INPUT_DIR", "input_images")
REDIS_OUTPUT_STREAM = os.getenv("REDIS_OUTPUT_STREAM", "photo.analysis.raw")
PHOTO_TASK_STREAM = os.getenv("PHOTO_TASK_STREAM", "photo.task.raw")  # Input stream for task dispatch
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "models/yolov8m.pt")  # Upgraded to YOLOv8 Medium for better accuracy
AGENT_NAME = os.getenv("AGENT_NAME", "photo-analysis-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "v1.0")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 10))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 5))

# MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/photo_analysis_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PhotoAnalysisError(Exception):
    """Custom exception for photo analysis errors."""
    pass

class RedisConnectionError(Exception):
    """Custom exception for Redis connection errors."""
    pass

def safe_redis_connection() -> Optional[redis.Redis]:
    """Safely establish Redis connection with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
            logger.info(f"Successfully connected to Redis at {REDIS_URL}")
            return redis_client
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis connection attempt {attempt + 1} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.critical("Failed to connect to Redis after all retries")
                return None
        except Exception as e:
            logger.error(f"Unexpected Redis error: {e}")
            return None

def safe_model_loading() -> Optional[YOLO]:
    """Safely load YOLO model with error handling."""
    try:
        model = YOLO(YOLO_MODEL_PATH)
        logger.info(f"Loaded YOLOv8 model from {YOLO_MODEL_PATH}")
        return model
    except FileNotFoundError:
        logger.error(f"Model file not found: {YOLO_MODEL_PATH}")
        logger.info("Attempting to download model...")
        try:
            model = YOLO(YOLO_MODEL_PATH)  # This will download if not found
            logger.info("Model downloaded successfully")
            return model
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            return None
    except Exception as e:
        logger.error(f"Failed to load YOLOv8 model: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def validate_image_file(image_path: str) -> bool:
    """Validate that image file exists and is readable."""
    try:
        if not os.path.exists(image_path):
            logger.error(f"Image file does not exist: {image_path}")
            return False
        
        if not os.path.isfile(image_path):
            logger.error(f"Path is not a file: {image_path}")
            return False
        
        # Try to open with PIL to validate image format
        with Image.open(image_path) as img:
            img.verify()
        
        # Check file size (prevent processing extremely large files)
        file_size = os.path.getsize(image_path)
        max_size = 50 * 1024 * 1024  # 50MB limit
        if file_size > max_size:
            logger.warning(f"Image file is very large ({file_size / 1024 / 1024:.1f}MB): {image_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Image validation failed for {image_path}: {e}")
        return False

def safe_image_loading(image_path: str) -> Optional[np.ndarray]:
    """Safely load image with comprehensive error handling."""
    try:
        if not validate_image_file(image_path):
            return None
        
        # Load with OpenCV
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"Failed to load image with OpenCV: {image_path}")
            return None
        
        # Check if image is empty or corrupted
        if image.size == 0:
            logger.error(f"Image is empty: {image_path}")
            return None
        
        logger.debug(f"Successfully loaded image: {image_path} (shape: {image.shape})")
        return image
        
    except Exception as e:
        logger.error(f"Image loading failed for {image_path}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

def detect_skin_region(image: np.ndarray, bbox: List[float]) -> Optional[List[int]]:
    """Detect skin regions to better separate hair and clothing areas."""
    try:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            logger.warning(f"Invalid bbox coordinates: {bbox}")
            return None
        
        region = image[y1:y2, x1:x2]
        if region.size == 0:
            logger.warning("Empty region extracted from bbox")
            return None
        
        # Convert to HSV for skin detection
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        
        # Skin color range in HSV
        lower_skin = np.array([0, 20, 70], dtype=np.uint8)
        upper_skin = np.array([20, 255, 255], dtype=np.uint8)
        
        # Create skin mask
        skin_mask = cv2.inRange(hsv_region, lower_skin, upper_skin)
        
        # Find contours of skin regions
        contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.debug("No skin regions detected")
            return None
        
        # Find the largest skin region (likely the face)
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Validate contour size (too small might be noise)
        if w < 10 or h < 10:
            logger.debug("Skin region too small, likely noise")
            return None
        
        # Return face region in original image coordinates
        return [x1 + x, y1 + y, x1 + x + w, y1 + y + h]
        
    except Exception as e:
        logger.warning(f"Skin detection failed: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return None

def get_dominant_color_clustered(image: np.ndarray, bbox: List[float], num_clusters: int = 3) -> str:
    """Extract dominant color using k-means clustering for better accuracy."""
    try:
        x1, y1, x2, y2 = map(int, bbox)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
        
        if x2 <= x1 or y2 <= y1:
            logger.warning(f"Invalid bbox for color analysis: {bbox}")
            return "unknown"
        
        region = image[y1:y2, x1:x2]
        if region.size == 0:
            logger.warning("Empty region for color analysis")
            return "unknown"
        
        # Reshape for clustering
        pixels = region.reshape(-1, 3).astype(np.float32)
        
        if len(pixels) < num_clusters:
            logger.warning(f"Not enough pixels for clustering: {len(pixels)} < {num_clusters}")
            return "unknown"
        
        # Apply k-means clustering
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
        _, labels, centers = cv2.kmeans(pixels, num_clusters, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # Find the cluster with the most pixels
        unique_labels, counts = np.unique(labels, return_counts=True)
        dominant_cluster = unique_labels[np.argmax(counts)]
        dominant_color = centers[dominant_cluster]
        
        # Convert to HSV for better classification
        dominant_color_bgr = np.uint8([[dominant_color]])
        dominant_color_hsv = cv2.cvtColor(dominant_color_bgr, cv2.COLOR_BGR2HSV)
        h, s, v = dominant_color_hsv[0][0]
        
        # Improved color classification
        if v < 30:
            return "black"
        elif v > 200 and s < 30:
            return "white"
        elif s < 50:
            if v < 100:
                return "black"
            elif v > 150:
                return "white"
            else:
                return "gray"
        else:
            if h < 10 or h > 170:
                return "red"
            elif 10 <= h < 25:
                return "orange"
            elif 25 <= h < 35:
                return "yellow"
            elif 35 <= h < 85:
                return "green"
            elif 85 <= h < 130:
                return "blue"
            elif 130 <= h < 170:
                return "purple"
            else:
                return "other"
                
    except Exception as e:
        logger.warning(f"Clustered color analysis failed: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return "unknown"

def analyze_hair_color_improved(image: np.ndarray, bbox: List[float]) -> str:
    """Analyze hair color with improved region detection."""
    try:
        x1, y1, x2, y2 = map(int, bbox)
        
        # Detect skin region to find face
        face_region = detect_skin_region(image, bbox)
        
        if face_region:
            # If we found a face, analyze the region above it for hair
            fx1, fy1, fx2, fy2 = face_region
            hair_bbox = [x1, y1, x2, fy1]  # Region above face
        else:
            # Fallback to upper 1/4 if no face detected
            hair_region_height = int((y2 - y1) * 0.25)
            hair_bbox = [x1, y1, x2, y1 + hair_region_height]
        
        hair_color = get_dominant_color_clustered(image, hair_bbox)
        
        # Map to common hair colors
        hair_color_mapping = {
            "black": "black",
            "brown": "brown", 
            "blonde": "blonde",
            "red": "red",
            "gray": "gray",
            "white": "white",
            "other": "brown"  # Default to brown for unclear cases
        }
        
        return hair_color_mapping.get(hair_color, "unknown")
        
    except Exception as e:
        logger.warning(f"Improved hair color analysis failed: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return "unknown"

def analyze_clothing_color_improved(image: np.ndarray, bbox: List[float]) -> str:
    """Analyze clothing color with improved region detection."""
    try:
        x1, y1, x2, y2 = map(int, bbox)
        
        # Detect skin region to find face
        face_region = detect_skin_region(image, bbox)
        
        if face_region:
            # If we found a face, analyze the region below it for clothing
            fx1, fy1, fx2, fy2 = face_region
            clothing_bbox = [x1, fy2, x2, y2]  # Region below face
        else:
            # Fallback to middle region if no face detected
            person_height = y2 - y1
            clothing_start = y1 + int(person_height * 0.3)
            clothing_end = y1 + int(person_height * 0.8)
            clothing_bbox = [x1, clothing_start, x2, clothing_end]
        
        clothing_color = get_dominant_color_clustered(image, clothing_bbox)
        
        # Map to common clothing colors
        clothing_color_mapping = {
            "red": "red",
            "blue": "blue",
            "green": "green", 
            "yellow": "yellow",
            "black": "black",
            "white": "white",
            "gray": "gray",
            "orange": "orange",
            "purple": "purple",
            "other": "unknown"
        }
        
        return clothing_color_mapping.get(clothing_color, "unknown")
        
    except Exception as e:
        logger.warning(f"Improved clothing color analysis failed: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return "unknown"

def analyze_gender_simple(image: np.ndarray, bbox: List[float]) -> str:
    """Simple gender analysis based on clothing patterns and colors."""
    try:
        clothing_color = analyze_clothing_color_improved(image, bbox)
        hair_color = analyze_hair_color_improved(image, bbox)
        
        # Very basic heuristic - this could be improved with ML
        # For now, return "unknown" as this requires more sophisticated analysis
        return "unknown"
    except Exception as e:
        logger.warning(f"Gender analysis failed: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return "unknown"

def analyze_faces(image_path: str) -> List[Dict[str, Any]]:
    """Analyze faces using face_recognition library."""
    if not FACE_RECOGNITION_AVAILABLE:
        logger.warning("Face recognition not available")
        return []
    
    try:
        # Load image
        image = face_recognition.load_image_file(image_path)
        
        # Find face locations
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        
        faces = []
        for i, (face_location, face_encoding) in enumerate(zip(face_locations, face_encodings)):
            top, right, bottom, left = face_location
            faces.append({
                "face_id": i,
                "bbox": [left, top, right, bottom],
                "encoding": face_encoding.tolist()  # Convert numpy array to list for JSON serialization
            })
        
        logger.debug(f"Detected {len(faces)} faces in {image_path}")
        return faces
        
    except Exception as e:
        logger.warning(f"Face analysis failed for {image_path}: {e}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return []

def safe_analyze_image(image_path: str) -> Dict[str, Any]:
    """Safely analyze image with comprehensive error handling."""
    try:
        # Validate and load image
        if not validate_image_file(image_path):
            return {
                "detections": [],
                "error": "Image validation failed",
                "error_type": "validation_error"
            }
        
        image = safe_image_loading(image_path)
        if image is None:
            return {
                "detections": [],
                "error": "Failed to load image",
                "error_type": "loading_error"
            }
        
        # YOLOv8 object detection
        try:
            results = model(image_path)
        except Exception as e:
            logger.error(f"YOLO detection failed for {image_path}: {e}")
            return {
                "detections": [],
                "error": f"Object detection failed: {str(e)}",
                "error_type": "detection_error"
            }
        
        detections = []
        person_count = 0
        
        for result in results:
            for box in result.boxes:
                try:
                    detection = {
                        "class": model.names[int(box.cls)],
                        "confidence": float(box.conf),
                        "bbox": [float(x) for x in box.xyxy[0].tolist()]
                    }
                    
                    # If it's a person, add detailed analysis
                    if detection["class"] == "person":
                        person_count += 1
                        
                        try:
                            # Analyze hair color
                            hair_color = analyze_hair_color_improved(image, detection["bbox"])
                            detection["hair_color"] = hair_color
                        except Exception as e:
                            logger.warning(f"Hair color analysis failed: {e}")
                            detection["hair_color"] = "unknown"
                        
                        try:
                            # Analyze clothing color
                            clothing_color = analyze_clothing_color_improved(image, detection["bbox"])
                            detection["clothing_color"] = clothing_color
                        except Exception as e:
                            logger.warning(f"Clothing color analysis failed: {e}")
                            detection["clothing_color"] = "unknown"
                        
                        try:
                            # Analyze gender (simplified)
                            gender = analyze_gender_simple(image, detection["bbox"])
                            detection["gender"] = gender
                        except Exception as e:
                            logger.warning(f"Gender analysis failed: {e}")
                            detection["gender"] = "unknown"
                        
                        # Add person-specific metadata
                        detection["person_id"] = person_count
                    
                    detections.append(detection)
                    
                except Exception as e:
                    logger.warning(f"Failed to process detection: {e}")
                    continue
        
        # Add overall person count to the analysis
        result = {"detections": detections}
        
        if person_count > 0:
            try:
                # Analyze faces for all people
                faces = analyze_faces(image_path)
                if faces:
                    result["person_analysis"] = {
                        "total_people": person_count,
                        "faces_detected": len(faces),
                        "face_encodings": faces
                    }
            except Exception as e:
                logger.warning(f"Face analysis failed: {e}")
                result["person_analysis"] = {
                    "total_people": person_count,
                    "faces_detected": 0,
                    "face_encodings": []
                }
        
        return result
        
    except Exception as e:
        logger.error(f"Image analysis failed for {image_path}: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "detections": [],
            "error": f"Analysis failed: {str(e)}",
            "error_type": "analysis_error"
        }

# safe_publish_to_redis function removed - now using RedisBus and StandardMessage format


def get_minio_client() -> Optional[Minio]:
    """Get MinIO client for downloading images."""
    if not MINIO_AVAILABLE:
        logger.warning("MinIO client not available")
        return None
    try:
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE
        )
        return client
    except Exception as e:
        logger.error(f"Failed to create MinIO client: {e}")
        return None


def download_image_from_url(url: str, temp_dir: str) -> Optional[str]:
    """
    Download image from URL (supports MinIO presigned URLs and HTTP URLs).
    Returns the local file path of the downloaded image.
    """
    try:
        # Generate temp file path
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or f"image_{int(time.time())}.jpg"
        local_path = os.path.join(temp_dir, filename)
        
        # Download via HTTP (works for presigned MinIO URLs)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        with open(local_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Downloaded image to: {local_path}")
        return local_path
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download image from URL {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading image: {e}")
        return None


def process_stream_task(bus: RedisBus, task: Dict[str, Any], temp_dir: str) -> Optional[Dict[str, Any]]:
    """
    Process a single task from the photo.task.raw stream.
    Downloads the image, analyzes it, and returns the result.
    """
    try:
        task_id = task.get("task_id", "unknown")
        image_url = task.get("image_url")
        filename = task.get("filename", "unknown")
        mission_id = task.get("mission_id")
        session_id = task.get("session_id")
        
        if not image_url:
            logger.error(f"Task {task_id} missing image_url")
            return {
                "task_id": task_id,
                "error": "Missing image_url in task",
                "error_type": "invalid_task"
            }
        
        logger.info(f"Processing task {task_id}: {filename}")
        
        # Download the image
        local_path = download_image_from_url(image_url, temp_dir)
        if not local_path:
            return {
                "task_id": task_id,
                "error": f"Failed to download image from {image_url}",
                "error_type": "download_error"
            }
        
        try:
            # Analyze the image
            analysis_result = safe_analyze_image(local_path)
            
            # Calculate SAR-specific metadata
            detections = analysis_result.get("detections", []) if isinstance(analysis_result, dict) else []
            person_analysis = analysis_result.get("person_analysis", {}) if isinstance(analysis_result, dict) else {}
            sar_metadata = calculate_sar_metadata(detections, person_analysis, local_path)
            
            result = {
                "task_id": task_id,
                "mission_id": mission_id,
                "session_id": session_id,
                "metadata": {
                    "agent_name": AGENT_NAME,
                    "agent_version": AGENT_VERSION,
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "source": "YOLOv8 + Color Analysis + Face Recognition + SAR Analysis",
                    "image_file": filename,
                    "image_url": image_url,
                    "capabilities": {
                        "object_detection": True,
                        "color_analysis": True,
                        "person_counting": True,
                        "face_analysis": FACE_RECOGNITION_AVAILABLE,
                        "sar_analysis": True
                    }
                },
                "detections": detections,
                "person_analysis": person_analysis,
                "sar_context": sar_metadata
            }
            
            # Add error information if present
            if "error" in analysis_result:
                result["error"] = analysis_result["error"]
                result["error_type"] = analysis_result.get("error_type", "unknown")
            
            return result
            
        finally:
            # Clean up downloaded file
            try:
                if os.path.exists(local_path):
                    os.remove(local_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {local_path}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to process stream task: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "task_id": task.get("task_id", "unknown"),
            "error": f"Task processing failed: {str(e)}",
            "error_type": "processing_error"
        }


def calculate_search_priority(detections: List[Dict[str, Any]], person_analysis: Dict[str, Any]) -> str:
    """Calculate search priority based on SAR-relevant factors."""
    try:
        priority_score = 0
        
        # Check for people (highest priority)
        people_count = person_analysis.get("total_people", 0)
        if people_count > 0:
            priority_score += 100 * people_count
        
        # Check for emergency equipment
        emergency_equipment = detect_emergency_equipment(detections)
        if emergency_equipment:
            priority_score += 50 * len(emergency_equipment)
        
        # Check for vehicles/boats (potential rescue resources)
        vehicles = [d for d in detections if d.get("class") in ["car", "truck", "boat", "motorcycle"]]
        if vehicles:
            priority_score += 30 * len(vehicles)
        
        # Check for water bodies (high risk)
        water_indicators = [d for d in detections if d.get("class") in ["boat", "person"]]
        if water_indicators:
            priority_score += 40
        
        # Determine priority level
        if priority_score >= 150:
            return "CRITICAL"
        elif priority_score >= 100:
            return "HIGH"
        elif priority_score >= 50:
            return "MEDIUM"
        else:
            return "LOW"
            
    except Exception as e:
        logger.warning(f"Search priority calculation failed: {e}")
        return "UNKNOWN"

def detect_emergency_equipment(detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect SAR-relevant emergency equipment."""
    try:
        emergency_keywords = [
            "life jacket", "life vest", "life ring", "flare", "radio", "phone", 
            "first aid", "medical", "rescue", "emergency", "safety", "helmet"
        ]
        
        emergency_equipment = []
        
        for detection in detections:
            class_name = detection.get("class", "").lower()
            
            # Check for emergency equipment in class name
            for keyword in emergency_keywords:
                if keyword in class_name:
                    emergency_equipment.append({
                        "type": class_name,
                        "confidence": detection.get("confidence", 0),
                        "bbox": detection.get("bbox", []),
                        "priority": "HIGH" if "life" in class_name or "flare" in class_name else "MEDIUM"
                    })
                    break
        
        return emergency_equipment
        
    except Exception as e:
        logger.warning(f"Emergency equipment detection failed: {e}")
        return []

def assess_accessibility(detections: List[Dict[str, Any]], image_path: str) -> Dict[str, Any]:
    """Assess terrain accessibility for SAR operations."""
    try:
        accessibility_score = 100  # Start with perfect accessibility
        
        # Check for terrain obstacles
        obstacles = [d for d in detections if d.get("class") in ["tree", "rock", "cliff", "mountain"]]
        if obstacles:
            accessibility_score -= 20 * len(obstacles)
        
        # Check for water bodies (may require boats)
        water_bodies = [d for d in detections if d.get("class") in ["boat", "water"]]
        if water_bodies:
            accessibility_score -= 30
        
        # Check for vehicles (good for access)
        vehicles = [d for d in detections if d.get("class") in ["car", "truck", "motorcycle"]]
        if vehicles:
            accessibility_score += 10 * len(vehicles)
        
        # Determine accessibility level
        if accessibility_score >= 80:
            accessibility_level = "EASY"
        elif accessibility_score >= 50:
            accessibility_level = "MODERATE"
        elif accessibility_score >= 20:
            accessibility_level = "DIFFICULT"
        else:
            accessibility_level = "VERY_DIFFICULT"
        
        return {
            "score": max(0, accessibility_score),
            "level": accessibility_level,
            "obstacles": len(obstacles),
            "water_present": len(water_bodies) > 0,
            "vehicle_access": len(vehicles) > 0
        }
        
    except Exception as e:
        logger.warning(f"Accessibility assessment failed: {e}")
        return {
            "score": 50,
            "level": "UNKNOWN",
            "obstacles": 0,
            "water_present": False,
            "vehicle_access": False
        }

def determine_urgency_level(detections: List[Dict[str, Any]], person_analysis: Dict[str, Any]) -> str:
    """Determine urgency level for SAR response."""
    try:
        urgency_factors = []
        
        # People detected (highest urgency)
        people_count = person_analysis.get("total_people", 0)
        if people_count > 0:
            urgency_factors.append(f"{people_count} person(s) detected")
        
        # Emergency equipment
        emergency_equipment = detect_emergency_equipment(detections)
        if emergency_equipment:
            urgency_factors.append(f"{len(emergency_equipment)} emergency equipment item(s)")
        
        # Water presence (high risk)
        water_indicators = [d for d in detections if d.get("class") in ["boat", "water"]]
        if water_indicators:
            urgency_factors.append("Water body detected")
        
        # Time-based factors (could be enhanced with actual time data)
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour > 20:  # Night time
            urgency_factors.append("Night time conditions")
        
        # Determine urgency level
        if len(urgency_factors) >= 3:
            return "IMMEDIATE"
        elif len(urgency_factors) >= 2:
            return "HIGH"
        elif len(urgency_factors) >= 1:
            return "MEDIUM"
        else:
            return "LOW"
            
    except Exception as e:
        logger.warning(f"Urgency level determination failed: {e}")
        return "UNKNOWN"

def analyze_weather_conditions(image_path: str) -> Dict[str, Any]:
    """Analyze image for weather indicators."""
    try:
        # This is a simplified weather analysis
        # In a real implementation, you might use specialized weather detection models
        
        weather_indicators = {
            "visibility": "GOOD",  # Could be enhanced with fog/dust detection
            "lighting": "DAY" if 6 <= datetime.now().hour <= 18 else "NIGHT",
            "weather_conditions": "UNKNOWN"
        }
        
        return weather_indicators
        
    except Exception as e:
        logger.warning(f"Weather analysis failed: {e}")
        return {
            "visibility": "UNKNOWN",
            "lighting": "UNKNOWN", 
            "weather_conditions": "UNKNOWN"
        }

def calculate_sar_metadata(detections: List[Dict[str, Any]], person_analysis: Dict[str, Any], image_path: str) -> Dict[str, Any]:
    """Calculate comprehensive SAR-specific metadata."""
    try:
        # Calculate all SAR metrics
        search_priority = calculate_search_priority(detections, person_analysis)
        emergency_equipment = detect_emergency_equipment(detections)
        accessibility = assess_accessibility(detections, image_path)
        urgency_level = determine_urgency_level(detections, person_analysis)
        weather_conditions = analyze_weather_conditions(image_path)
        
        # Calculate response time estimate
        response_time_estimate = "IMMEDIATE" if urgency_level == "IMMEDIATE" else \
                               "WITHIN_1_HOUR" if urgency_level == "HIGH" else \
                               "WITHIN_4_HOURS" if urgency_level == "MEDIUM" else "ROUTINE"
        
        return {
            "search_priority": search_priority,
            "emergency_equipment": emergency_equipment,
            "accessibility": accessibility,
            "urgency_level": urgency_level,
            "weather_conditions": weather_conditions,
            "response_time_estimate": response_time_estimate,
            "sar_metrics": {
                "people_count": person_analysis.get("total_people", 0),
                "faces_detected": person_analysis.get("faces_detected", 0),
                "equipment_count": len(emergency_equipment),
                "vehicle_count": len([d for d in detections if d.get("class") in ["car", "truck", "boat", "motorcycle"]]),
                "terrain_complexity": "HIGH" if accessibility["level"] in ["DIFFICULT", "VERY_DIFFICULT"] else "LOW"
            }
        }
        
    except Exception as e:
        logger.error(f"SAR metadata calculation failed: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "search_priority": "UNKNOWN",
            "emergency_equipment": [],
            "accessibility": {"score": 50, "level": "UNKNOWN"},
            "urgency_level": "UNKNOWN",
            "weather_conditions": {"visibility": "UNKNOWN", "lighting": "UNKNOWN"},
            "response_time_estimate": "UNKNOWN",
            "sar_metrics": {"people_count": 0, "faces_detected": 0, "equipment_count": 0, "vehicle_count": 0, "terrain_complexity": "UNKNOWN"}
        }

def main():
    """Main function with comprehensive error handling."""
    logger.info(f"{AGENT_NAME} {AGENT_VERSION} starting up.")
    logger.info(f"Monitoring directory: {IMAGE_INPUT_DIR}")
    logger.info(f"Listening to stream: {PHOTO_TASK_STREAM}")
    logger.info(f"Face analysis: {'Available' if FACE_RECOGNITION_AVAILABLE else 'Not available'}")
    
    # Initialize RedisBus for StandardMessage format
    bus = RedisBus(REDIS_URL)
    if not bus:
        logger.critical("Cannot start agent without Redis connection")
        exit(1)
    
    # Get raw Redis client for stream reading
    redis_client = safe_redis_connection()
    if not redis_client:
        logger.critical("Cannot start agent without Redis connection")
        exit(1)
    
    global model
    model = safe_model_loading()
    if model is None:
        logger.critical("Cannot start agent without YOLO model")
        exit(1)
    
    processed_files = set()
    processed_stream_ids = set()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    # Create temp directory for downloaded images
    temp_dir = tempfile.mkdtemp(prefix="photo_analysis_")
    logger.info(f"Using temp directory: {temp_dir}")
    
    try:
        while True:
            try:
                # =============================================
                # PART 1: Process tasks from stream (priority)
                # =============================================
                try:
                    # Read latest messages from task stream
                    stream_messages = redis_client.xrevrange(PHOTO_TASK_STREAM, count=10)
                    
                    for msg_id, msg_data in stream_messages:
                        if msg_id in processed_stream_ids:
                            continue
                        
                        try:
                            # Parse the message
                            if "data" in msg_data:
                                data = json.loads(msg_data["data"])
                                payload = data.get("payload", data)
                            else:
                                payload = msg_data
                            
                            task_id = payload.get("task_id", "unknown")
                            logger.info(f"Processing stream task: {task_id}")
                            
                            # Process the task
                            result = process_stream_task(bus, payload, temp_dir)
                            
                            if result:
                                # Print to console
                                print(f"\n=== Photo Analysis Output (Task: {task_id}) ===")
                                print(json.dumps(result, indent=2))
                                print("================================================\n")
                                
                                # Publish result to output stream
                                try:
                                    standard_message = wrap_envelope(
                                        payload=result,
                                        source_name=AGENT_NAME,
                                        source_version=AGENT_VERSION,
                                        target_stream=REDIS_OUTPUT_STREAM
                                    )
                                    bus.publish(standard_message)
                                    logger.info(f"Published analysis for task {task_id} to {REDIS_OUTPUT_STREAM}")
                                    
                                    # Also store result with task_id for retrieval
                                    redis_client.hset(f"task:{task_id}", mapping={
                                        "status": "completed",
                                        "result": json.dumps(result),
                                        "completed_at": datetime.utcnow().isoformat() + "Z"
                                    })
                                    redis_client.expire(f"task:{task_id}", 3600)  # 1 hour TTL
                                    
                                except Exception as e:
                                    logger.error(f"Failed to publish results for task {task_id}: {e}")
                            
                            processed_stream_ids.add(msg_id)
                            consecutive_errors = 0
                            
                        except Exception as e:
                            consecutive_errors += 1
                            logger.error(f"Error processing stream message {msg_id}: {e}")
                            logger.error(f"Traceback: {traceback.format_exc()}")
                            processed_stream_ids.add(msg_id)  # Mark as processed to avoid retry loop
                            
                except redis.exceptions.ResponseError as e:
                    # Stream might not exist yet
                    if "NOGROUP" not in str(e) and "no such key" not in str(e).lower():
                        logger.error(f"Redis error reading stream: {e}")
                except Exception as e:
                    logger.error(f"Error reading from task stream: {e}")
                
                # =============================================
                # PART 2: Monitor directory for new files
                # =============================================
                try:
                    files = [f for f in os.listdir(IMAGE_INPUT_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
                except FileNotFoundError:
                    os.makedirs(IMAGE_INPUT_DIR, exist_ok=True)
                    files = []
                except Exception as e:
                    logger.error(f"Error reading input directory: {e}")
                    time.sleep(UPDATE_INTERVAL_SECONDS)
                    continue
                
                new_files = [f for f in files if f not in processed_files]
                
                for filename in new_files:
                    try:
                        image_path = os.path.join(IMAGE_INPUT_DIR, filename)
                        logger.info(f"Analyzing image from directory: {image_path}")
                        
                        analysis_result = safe_analyze_image(image_path)
                        
                        # Calculate SAR-specific metadata
                        detections = analysis_result.get("detections", []) if isinstance(analysis_result, dict) else []
                        person_analysis = analysis_result.get("person_analysis", {}) if isinstance(analysis_result, dict) else {}
                        sar_metadata = calculate_sar_metadata(detections, person_analysis, image_path)
                        
                        message = {
                            "metadata": {
                                "agent_name": AGENT_NAME,
                                "agent_version": AGENT_VERSION,
                                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                                "source": "YOLOv8 + Color Analysis + Face Recognition + SAR Analysis",
                                "image_file": filename,
                                "capabilities": {
                                    "object_detection": True,
                                    "color_analysis": True,
                                    "person_counting": True,
                                    "face_analysis": FACE_RECOGNITION_AVAILABLE,
                                    "sar_analysis": True
                                }
                            },
                            "detections": detections,
                            "person_analysis": person_analysis,
                            "sar_context": sar_metadata
                        }
                        
                        # Add error information if present
                        if "error" in analysis_result:
                            message["error"] = analysis_result["error"]
                            message["error_type"] = analysis_result.get("error_type", "unknown")
                        
                        # Print the full output to the console in a readable format
                        print("\n=== Photo Analysis Output ===")
                        print(json.dumps(message, indent=2))
                        print("============================\n")
                        
                        # Publish to Redis using StandardMessage format
                        try:
                            standard_message = wrap_envelope(
                                payload=message,
                                source_name=AGENT_NAME,
                                source_version=AGENT_VERSION,
                                target_stream=REDIS_OUTPUT_STREAM
                            )
                            bus.publish(standard_message)
                            logger.info(f"Successfully published analysis for {filename} to {REDIS_OUTPUT_STREAM}")
                        except Exception as e:
                            logger.error(f"Failed to publish results for {filename}: {e}")
                        
                        processed_files.add(filename)
                        consecutive_errors = 0  # Reset error counter on success
                        
                    except Exception as e:
                        consecutive_errors += 1
                        logger.error(f"Error processing {filename}: {e}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        
                        # Add to processed files to avoid infinite retry
                        processed_files.add(filename)
                        
                        if consecutive_errors >= max_consecutive_errors:
                            logger.critical(f"Too many consecutive errors ({consecutive_errors}), exiting")
                            exit(1)
                
                # Limit growth of processed_stream_ids set
                if len(processed_stream_ids) > 10000:
                    processed_stream_ids.clear()
                    logger.info("Cleared processed stream IDs cache")
                
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down gracefully")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
    finally:
        # Clean up temp directory
        try:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory: {e}")


if __name__ == "__main__":
    main() 