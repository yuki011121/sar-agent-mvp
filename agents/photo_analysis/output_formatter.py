"""
Output formatting module for the photo analysis agent.
Handles creation of structured JSON output and metadata.
"""

import os
import uuid
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

class OutputFormatter:
    """Handles output formatting and metadata creation."""
    
    def __init__(self, redis_output_stream: str, 
                 output_mode: str = "compact",
                 include_debug: bool = False,
                 class_allowlist: Optional[List[str]] = None,
                 confidence_threshold: float = 0.50):
        """Initialize the output formatter."""
        self.redis_output_stream = redis_output_stream
        self.output_mode = output_mode
        self.include_debug = include_debug
        self.class_allowlist = class_allowlist or ["person", "vehicle", "boat", "car", "truck", "motorcycle"]
        self.confidence_threshold = confidence_threshold
    
    def filter_detections(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter detections based on confidence threshold and class allowlist."""
        filtered = []
        for detection in detections:
            # Check confidence threshold
            if detection.get("confidence", 0.0) < self.confidence_threshold:
                continue
            
            # Check class allowlist
            detection_type = detection.get("type", "unknown")
            if self.class_allowlist and detection_type not in self.class_allowlist:
                continue
            
            # Clean up detection for compact mode
            if self.output_mode == "compact":
                detection = self._clean_detection(detection)
            
            filtered.append(detection)
        
        return filtered
    
    def _clean_detection(self, detection: Dict[str, Any]) -> Dict[str, Any]:
        """Clean detection for compact mode by removing empty/unnecessary fields."""
        cleaned = {
            "id": detection.get("id"),
            "type": detection.get("type"),
            "confidence": round(detection.get("confidence", 0.0), 3),
            "bbox": detection.get("bbox")
        }
        
        # Only include attributes if they have meaningful content
        attributes = detection.get("attributes", {})
        if attributes:
            clean_attributes = {}
            
            # Appearance attributes
            appearance = attributes.get("appearance", {})
            if appearance and any(v for v in appearance.values() if v and v != "unknown"):
                clean_attributes["appearance"] = appearance
            
            # Only include face if present
            face = attributes.get("face", {})
            if face and face.get("present", False):
                # In compact mode, exclude full encoding (too large) but keep metadata
                clean_face = {
                    "present": True,
                    "encoding_id": face.get("encoding_id"),
                    "quality": face.get("quality", {})
                }
                # Only include encoding in full mode or debug mode
                if self.output_mode == "full" or self.include_debug:
                    clean_face["encoding"] = face.get("encoding")
                    if face.get("bbox"):
                        clean_face["bbox"] = face.get("bbox")
                clean_attributes["face"] = clean_face
            
            # Only include equipment if present
            equipment = attributes.get("equipment", [])
            if equipment:
                clean_attributes["equipment"] = equipment
            
            if clean_attributes:
                cleaned["attributes"] = clean_attributes
        
        return cleaned
    
    def create_aggregates(self, detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create aggregates section with counts and confidence averages."""
        try:
            counts = {}
            confidence_sums = {}
            confidence_counts = {}
            
            for detection in detections:
                detection_type = detection.get("type", "unknown")
                confidence = detection.get("confidence", 0.0)
                
                # Count by type
                counts[detection_type] = counts.get(detection_type, 0) + 1
                
                # Calculate average confidence
                if detection_type not in confidence_sums:
                    confidence_sums[detection_type] = 0.0
                    confidence_counts[detection_type] = 0
                confidence_sums[detection_type] += confidence
                confidence_counts[detection_type] += 1
            
            # Calculate averages
            class_confidence_avg = {}
            for detection_type in confidence_sums:
                if confidence_counts[detection_type] > 0:
                    class_confidence_avg[detection_type] = round(
                        confidence_sums[detection_type] / confidence_counts[detection_type], 3
                    )
            
            result = {"counts": counts}
            
            # Only include confidence averages in debug mode
            if self.include_debug:
                result["class_confidence_avg"] = class_confidence_avg
            
            return result
            
        except Exception as e:
            logger.warning(f"Aggregates calculation failed: {e}")
            return {"counts": {}}
    
    def create_image_metadata(self, image_path: str, image: np.ndarray, model_input_size: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Create image metadata section."""
        try:
            filename = os.path.basename(image_path)
            height, width = image.shape[:2]
            
            metadata = {
                "id": f"img_{str(uuid.uuid4())[:8]}",
                "filename": filename,
                "original_size": {"w": width, "h": height}
            }
            
            # Add model input size if available
            if model_input_size:
                metadata["model_input_size"] = model_input_size
            elif self.include_debug:
                metadata["model_input_size"] = {"w": width, "h": height}
            
            # Only include additional metadata in full mode or debug mode
            if self.output_mode == "full" or self.include_debug:
                metadata.update({
                    "source": "uav_camera_1",  # Default source
                    "capture_time": datetime.utcnow().isoformat() + "Z",
                    "geo": {
                        "lat": 35.305,  # Default coordinates (rounded)
                        "lon": -120.6625
                    }
                })
            else:
                # Compact mode - minimal geo info
                metadata["geo"] = {"lat": 35.305, "lon": -120.6625}
            
            return metadata
            
        except Exception as e:
            logger.warning(f"Image metadata creation failed: {e}")
            return {
                "id": f"img_{str(uuid.uuid4())[:8]}",
                "filename": os.path.basename(image_path),
                "original_size": {"w": 0, "h": 0},
                "geo": {"lat": 0.0, "lon": 0.0}
            }
    
    def create_processing_metadata(self, runtime_ms: float) -> Dict[str, Any]:
        """Create processing metadata section."""
        processing = {
            "agent": "photo-analysis",
            "runtime_ms": round(runtime_ms, 1)
        }
        
        # Only include detailed info in full mode or debug mode
        if self.output_mode == "full" or self.include_debug:
            processing.update({
                "models": {
                    "yolov8": "v8m-2024.01",  # YOLOv8 Medium version
                    "opencv": "4.8.0"
                },
                "capabilities": {
                    "object_detection": True,
                    "color_analysis": True,
                    "face_encoding": True,  # DeepFace integration
                    "sar_assessment": True
                },
                "errors": []
            })
        else:
            # Compact mode - minimal processing info
            processing["capabilities"] = {
                "object_detection": True,
                "color_analysis": True,
                "face_encoding": True,  # DeepFace integration
                "sar_assessment": True
            }
        
        return processing
    
    def format_output(self, 
                     image_path: str, 
                     image: np.ndarray, 
                     detections: List[Dict[str, Any]], 
                     sar_metadata: Dict[str, Any], 
                     sar_assessment: Dict[str, Any], 
                     runtime_ms: float,
                     model_input_size: Optional[Dict[str, int]] = None,
                     errors: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Create the complete structured output."""
        try:
            # Filter and clean detections
            filtered_detections = self.filter_detections(detections)
            
            # Create all sections
            image_metadata = self.create_image_metadata(image_path, image, model_input_size)
            processing_metadata = self.create_processing_metadata(runtime_ms)
            aggregates = self.create_aggregates(filtered_detections)
            
            # Add errors to processing metadata if any
            if errors and (self.output_mode == "full" or self.include_debug):
                processing_metadata["errors"] = errors
            
            # Create the complete message
            message = {
                "version": "1.0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "stream": self.redis_output_stream,
                "image": image_metadata,
                "processing": processing_metadata,
                "detections": filtered_detections,
                "aggregates": aggregates,
                "sar_assessment": sar_assessment
            }
            
            return message
            
        except Exception as e:
            logger.error(f"Output formatting failed: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "version": "1.0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "stream": self.redis_output_stream,
                "error": f"Output formatting failed: {str(e)}"
            }
