"""
Main photo analysis agent module.
Coordinates image analysis, color analysis, SAR assessment, and output formatting.
"""

import os
import time
import logging
import json
import traceback
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any

# Import our custom modules (relative imports for package execution)
from .image_analyzer import ImageAnalyzer
from .color_analyzer import ColorAnalyzer
from .sar_assessor import SARAssessor
from .output_formatter import OutputFormatter
from .redis_client import RedisClient
from .face_recognition import FaceRecognizer

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
IMAGE_INPUT_DIR = os.getenv("IMAGE_INPUT_DIR", "input_images")
REDIS_OUTPUT_STREAM = os.getenv("REDIS_OUTPUT_STREAM", "photo.analysis.raw")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8m.pt")
AGENT_VERSION = "photo-analysis-agent-v1.0"
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 10))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 5))
FACE_MODEL = os.getenv("FACE_MODEL", "VGG-Face")  # DeepFace model name
ENABLE_FACE_RECOGNITION = os.getenv("ENABLE_FACE_RECOGNITION", "true").lower() == "true"

# Output formatting configuration
OUTPUT_MODE = os.getenv("OUTPUT_MODE", "compact")  # compact|full
INCLUDE_DEBUG = os.getenv("INCLUDE_DEBUG", "false").lower() == "true"
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.50"))
CLASS_ALLOWLIST = os.getenv("CLASS_ALLOWLIST", "person,vehicle,boat,car,truck,motorcycle").split(",")

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('photo_analysis_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PhotoAnalysisAgent:
    """Main photo analysis agent class."""
    
    def __init__(self):
        """Initialize the photo analysis agent."""
        self.image_analyzer = None
        self.color_analyzer = ColorAnalyzer()
        self.sar_assessor = SARAssessor()
        self.face_recognizer = FaceRecognizer(model_name=FACE_MODEL) if ENABLE_FACE_RECOGNITION else None
        self.output_formatter = OutputFormatter(
            redis_output_stream=REDIS_OUTPUT_STREAM,
            output_mode=OUTPUT_MODE,
            include_debug=INCLUDE_DEBUG,
            class_allowlist=CLASS_ALLOWLIST,
            confidence_threshold=CONFIDENCE_THRESHOLD
        )
        self.redis_client = RedisClient(REDIS_URL, REDIS_OUTPUT_STREAM, MAX_RETRIES, RETRY_DELAY)
        self.processed_files = set()
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
    
    def initialize(self) -> bool:
        """Initialize all components."""
        logger.info(f"{AGENT_VERSION} starting up. Monitoring {IMAGE_INPUT_DIR} for new images.")
        
        # Initialize image analyzer
        self.image_analyzer = ImageAnalyzer(YOLO_MODEL_PATH)
        if self.image_analyzer.model is None:
            logger.critical("Cannot start agent without YOLO model")
            return False
        
        # Initialize Redis connection
        if not self.redis_client.connect():
            logger.critical("Cannot start agent without Redis connection")
            return False
        
        logger.info("All components initialized successfully")
        return True
    
    def process_image(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Process a single image and return structured output."""
        try:
            logger.info(f"Analyzing image: {image_path}")
            start_time = time.time()
            
            # Run image analysis
            analysis_result = self.image_analyzer.analyze_image(image_path)
            
            # Check for errors
            if "error" in analysis_result:
                logger.error(f"Image analysis failed: {analysis_result['error']}")
                return None
            
            # Get image for metadata and color analysis
            image = self.image_analyzer.load_image(image_path)
            if image is None:
                image = np.zeros((100, 100, 3), dtype=np.uint8)  # Fallback
            
            # Enhance person detections with color analysis
            detections = analysis_result.get("detections", [])
            if detections:
                detections = self.color_analyzer.enhance_person_detection(image, detections)
                
                # Enhance person detections with face recognition
                if self.face_recognizer and self.face_recognizer.enabled:
                    detections = self.face_recognizer.enhance_person_detection_with_faces(image, detections)
            
            # Calculate SAR metadata
            person_analysis = analysis_result.get("person_analysis", {})
            sar_metadata = self.sar_assessor.calculate_sar_metadata(detections, person_analysis, image_path)
            
            # Create SAR assessment
            sar_assessment = self.sar_assessor.create_sar_assessment(sar_metadata, detections)
            
            # Calculate runtime
            runtime_ms = round((time.time() - start_time) * 1000, 1)
            
            # Format output
            message = self.output_formatter.format_output(
                image_path=image_path,
                image=image,
                detections=detections,
                sar_metadata=sar_metadata,
                sar_assessment=sar_assessment,
                runtime_ms=runtime_ms
            )
            
            return message
            
        except Exception as e:
            logger.error(f"Error processing {image_path}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def run(self):
        """Main processing loop."""
        if not self.initialize():
            return
        
        while True:
            try:
                # Check for new files
                try:
                    files = [f for f in os.listdir(IMAGE_INPUT_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
                except FileNotFoundError:
                    os.makedirs(IMAGE_INPUT_DIR, exist_ok=True)
                    files = []
                except Exception as e:
                    logger.error(f"Error reading input directory: {e}")
                    time.sleep(UPDATE_INTERVAL_SECONDS)
                    continue
                
                new_files = [f for f in files if f not in self.processed_files]
                
                for filename in new_files:
                    try:
                        image_path = os.path.join(IMAGE_INPUT_DIR, filename)
                        
                        # Process the image
                        message = self.process_image(image_path)
                        
                        if message:
                            # Print the full output to the console in a readable format
                            print("\n=== Photo Analysis Output ===")
                            print(json.dumps(message, indent=2))
                            print("============================\n")
                            
                            # Publish to Redis
                            if not self.redis_client.publish_message(message):
                                logger.error(f"Failed to publish results for {filename}")
                            
                            self.processed_files.add(filename)
                            self.consecutive_errors = 0  # Reset error counter on success
                        else:
                            # Add to processed files to avoid infinite retry
                            self.processed_files.add(filename)
                            self.consecutive_errors += 1
                            
                            if self.consecutive_errors >= self.max_consecutive_errors:
                                logger.critical(f"Too many consecutive errors ({self.consecutive_errors}), exiting")
                                return
                    
                    except Exception as e:
                        self.consecutive_errors += 1
                        logger.error(f"Error processing {filename}: {e}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        
                        # Add to processed files to avoid infinite retry
                        self.processed_files.add(filename)
                        
                        if self.consecutive_errors >= self.max_consecutive_errors:
                            logger.critical(f"Too many consecutive errors ({self.consecutive_errors}), exiting")
                            return
                
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down gracefully")
                break
            except Exception as e:
<<<<<<< HEAD
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
    logger.info(f"{AGENT_VERSION} starting up. Monitoring {IMAGE_INPUT_DIR} for new images.")
    logger.info(f"Face analysis: {'Available' if FACE_RECOGNITION_AVAILABLE else 'Not available'}")
    
    # Initialize RedisBus for StandardMessage format
    bus = RedisBus(REDIS_URL)
    if not bus:
        logger.critical("Cannot start agent without Redis connection")
        exit(1)
    
    global model
    model = safe_model_loading()
    if model is None:
        logger.critical("Cannot start agent without YOLO model")
        exit(1)
    
    processed_files = set()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            # Check for new files
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
                    logger.info(f"Analyzing image: {image_path}")
                    
                    analysis_result = safe_analyze_image(image_path)
                    
                    # Calculate SAR-specific metadata
                    detections = analysis_result.get("detections", []) if isinstance(analysis_result, dict) else []
                    person_analysis = analysis_result.get("person_analysis", {}) if isinstance(analysis_result, dict) else {}
                    sar_metadata = calculate_sar_metadata(detections, person_analysis, image_path)
                    
                    message = {
                        "metadata": {
                            "agent_name": AGENT_VERSION,
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
                            source_name="photo-analysis-agent",
                            source_version="v1.0",
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
            
            time.sleep(UPDATE_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down gracefully")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            time.sleep(UPDATE_INTERVAL_SECONDS)
=======
                logger.error(f"Unexpected error in main loop: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                time.sleep(UPDATE_INTERVAL_SECONDS)
    
    def shutdown(self):
        """Shutdown the agent gracefully."""
        logger.info("Shutting down photo analysis agent")
        self.redis_client.disconnect()

def main():
    """Main function."""
    agent = PhotoAnalysisAgent()
    try:
        agent.run()
    finally:
        agent.shutdown()
>>>>>>> 9965318 (feat: Add DeepFace integration for face recognition)

if __name__ == "__main__":
    main()