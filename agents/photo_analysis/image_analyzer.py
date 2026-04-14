"""
Image analysis module for the photo analysis agent.
Handles image loading, validation, and basic YOLO detection.
"""

import os
import logging
import traceback
from typing import Dict, List, Optional, Any
import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class ImageAnalyzer:
    """Handles image analysis operations."""
    
    def __init__(self, model_path: str):
        """Initialize the image analyzer with a YOLO model."""
        self.model = self._load_model(model_path)
    
    def _load_model(self, model_path: str) -> Optional[YOLO]:
        """Safely load YOLO model with error handling."""
        try:
            model = YOLO(model_path)
            logger.info(f"Loaded YOLOv8 model from {model_path}")
            return model
        except FileNotFoundError:
            logger.error(f"Model file not found: {model_path}")
            logger.info("Attempting to download model...")
            try:
                model = YOLO(model_path)  # This will download if not found
                logger.info("Model downloaded successfully")
                return model
            except Exception as e:
                logger.error(f"Failed to download model: {e}")
                return None
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 model: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def validate_image_file(self, image_path: str) -> bool:
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
    
    def load_image(self, image_path: str) -> Optional[np.ndarray]:
        """Safely load image with comprehensive error handling."""
        try:
            if not self.validate_image_file(image_path):
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
    
    def detect_objects(self, image_path: str) -> List[Dict[str, Any]]:
        """Run YOLO object detection on an image."""
        if self.model is None:
            logger.error("YOLO model not loaded")
            return []
        
        try:
            results = self.model(image_path)
            detections = []
            detection_id = 1
            
            for result in results:
                for box in result.boxes:
                    try:
                        # Convert bbox to new format
                        bbox_coords = [float(x) for x in box.xyxy[0].tolist()]
                        x1, y1, x2, y2 = bbox_coords
                        
                        detection = {
                            "id": f"det_{detection_id}",
                            "type": self.model.names[int(box.cls)],
                            "confidence": float(box.conf),
                            "bbox": {
                                "x": int(x1),
                                "y": int(y1), 
                                "w": int(x2 - x1),
                                "h": int(y2 - y1)
                            },
                            "bbox_coords": bbox_coords,  # Keep original coords for color analysis
                            "attributes": {
                                "appearance": {},
                                "face": {
                                    "present": False,
                                    "encoding_id": None,
                                    "quality": {
                                        "blur_score": 0.0,
                                        "occlusion": False
                                    }
                                },
                                "equipment": []
                            }
                        }
                        
                        detections.append(detection)
                        detection_id += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to process detection: {e}")
                        continue
            
            return detections
            
        except Exception as e:
            logger.error(f"YOLO detection failed for {image_path}: {e}")
            return []
    
    def analyze_image(self, image_path: str) -> Dict[str, Any]:
        """Complete image analysis with error handling."""
        try:
            # Validate and load image
            if not self.validate_image_file(image_path):
                return {
                    "detections": [],
                    "error": "Image validation failed",
                    "error_type": "validation_error"
                }
            
            image = self.load_image(image_path)
            if image is None:
                return {
                    "detections": [],
                    "error": "Failed to load image",
                    "error_type": "loading_error"
                }
            
            # Run object detection
            detections = self.detect_objects(image_path)
            
            # Count people
            person_count = len([d for d in detections if d.get("type") == "person"])
            
            result = {"detections": detections}
            if person_count > 0:
                result["person_analysis"] = {"total_people": person_count}
            
            return result
            
        except Exception as e:
            logger.error(f"Image analysis failed for {image_path}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "detections": [],
                "error": f"Analysis failed: {str(e)}",
                "error_type": "analysis_error"
            }
