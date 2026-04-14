"""
Face recognition module for the photo analysis agent.
Uses DeepFace for face detection, encoding, and recognition.
"""

import logging
import traceback
from typing import List, Optional, Dict, Any, Tuple
import cv2
import numpy as np

# Try to import DeepFace, but handle gracefully if not available
try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DeepFace = None
    DEEPFACE_AVAILABLE = False

logger = logging.getLogger(__name__)

class FaceRecognizer:
    """Handles face recognition using DeepFace."""
    
    def __init__(self, model_name: str = "VGG-Face", enforce_detection: bool = False):
        """
        Initialize the face recognizer.
        
        Args:
            model_name: DeepFace model to use (VGG-Face, Facenet, OpenFace, etc.)
            enforce_detection: If True, raise error if no face detected. If False, return None gracefully.
        """
        self.model_name = model_name
        self.enforce_detection = enforce_detection
        self.enabled = True
        
        # Check if DeepFace is available
        if not DEEPFACE_AVAILABLE:
            logger.warning("DeepFace not available, face recognition disabled. Install with: poetry add deepface")
            self.enabled = False
        else:
            logger.info(f"Face recognition initialized with model: {model_name}")
    
    def detect_faces(self, image: np.ndarray, person_bbox: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        """
        Detect faces in an image or within a person bounding box.
        
        Args:
            image: Full image as numpy array (BGR format)
            person_bbox: Optional bounding box [x1, y1, x2, y2] to crop person region first
            
        Returns:
            List of face detection dictionaries with bbox, confidence, and region
        """
        if not self.enabled:
            return []
        
        try:
            # Crop to person region if provided
            if person_bbox:
                x1, y1, x2, y2 = map(int, person_bbox)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(image.shape[1], x2), min(image.shape[0], y2)
                
                if x2 <= x1 or y2 <= y1:
                    logger.warning(f"Invalid person bbox for face detection: {person_bbox}")
                    return []
                
                person_region = image[y1:y2, x1:x2]
            else:
                person_region = image
            
            # Use DeepFace to detect faces
            # DeepFace expects RGB, but we have BGR from OpenCV
            person_region_rgb = cv2.cvtColor(person_region, cv2.COLOR_BGR2RGB)
            
            try:
                if not DEEPFACE_AVAILABLE or DeepFace is None:
                    return []
                
                # Try to detect faces - this may return multiple faces
                # DeepFace.extract_faces (>=0.0.84) returns a list of dict-like objects
                # with keys such as "face", "facial_area", and optionally "confidence".
                face_images = DeepFace.extract_faces(
                    person_region_rgb,
                    detector_backend='opencv',  # Fast and reliable
                    enforce_detection=self.enforce_detection,
                    align=True
                )

                faces = []
                for idx, face_obj in enumerate(face_images):
                    # Support both dict-like outputs (current DeepFace) and raw ndarray
                    face_img = face_obj
                    bbox = None
                    confidence = 1.0

                    if isinstance(face_obj, dict):
                        # Extract cropped face image
                        if "face" in face_obj:
                            face_img = face_obj["face"]

                        # Extract bounding box (facial_area) from DeepFace, if available
                        facial_area = face_obj.get("facial_area")
                        if facial_area is not None:
                            # facial_area may be a dict with x, y, w, h
                            if isinstance(facial_area, dict):
                                x = facial_area.get("x")
                                y = facial_area.get("y")
                                w = facial_area.get("w")
                                h = facial_area.get("h")
                                if None not in (x, y, w, h):
                                    x1_face = int(x)
                                    y1_face = int(y)
                                    x2_face = x1_face + int(w)
                                    y2_face = y1_face + int(h)
                                    bbox = [x1_face, y1_face, x2_face, y2_face]
                            # or a list/tuple [x1, y1, x2, y2] or [x, y, w, h]
                            elif isinstance(facial_area, (list, tuple)) and len(facial_area) == 4:
                                fa0, fa1, fa2, fa3 = facial_area
                                # Heuristically treat as [x, y, w, h] if third value is width-like
                                if fa2 >= 0 and fa3 >= 0:
                                    x1_face = int(fa0)
                                    y1_face = int(fa1)
                                    x2_face = x1_face + int(fa2)
                                    y2_face = y1_face + int(fa3)
                                    bbox = [x1_face, y1_face, x2_face, y2_face]

                        confidence = face_obj.get("confidence", 1.0)

                    face_info = {
                        "face_id": idx,
                        "region": face_img,  # Face image as numpy array (RGB format)
                        # bbox is relative to person_region_rgb for now; will offset below
                        "bbox": bbox,
                        "confidence": float(confidence) if confidence is not None else 1.0,
                    }
                    faces.append(face_info)

                # If we have person_bbox, adjust face coordinates to full-image space
                if person_bbox and faces:
                    x1_person, y1_person, x2_person, y2_person = map(int, person_bbox)
                    person_height = y2_person - y1_person
                    person_width = x2_person - x1_person

                    for face in faces:
                        if face["bbox"] is not None:
                            # Offset DeepFace bbox (relative to person_region_rgb)
                            fx1, fy1, fx2, fy2 = map(int, face["bbox"])
                            face["bbox"] = [
                                x1_person + fx1,
                                y1_person + fy1,
                                x1_person + fx2,
                                y1_person + fy2,
                            ]
                        else:
                            # Fallback: estimate face bbox (typically in upper portion of person)
                            # Rough estimate: face is usually in upper 1/3 of person region
                            face_height = int(person_height * 0.3)
                            face_width = int(face_height * 0.75)  # Typical face aspect ratio
                            face_x = x1_person + (person_width - face_width) // 2
                            face_y = y1_person + int(person_height * 0.1)

                            face["bbox"] = [
                                face_x,
                                face_y,
                                face_x + face_width,
                                face_y + face_height,
                            ]
                return faces
                
            except ValueError as e:
                # No face detected
                if "Face could not be detected" in str(e) or "could not detect a face" in str(e).lower():
                    logger.debug(f"No face detected in person region: {e}")
                    return []
                else:
                    raise
                    
        except Exception as e:
            logger.warning(f"Face detection failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return []
    
    def encode_face(self, face_image: np.ndarray) -> Optional[np.ndarray]:
        """
        Generate face encoding/embedding for a detected face.
        
        Args:
            face_image: Face image as numpy array (RGB format)
            
        Returns:
            Face encoding vector or None if encoding fails
        """
        if not self.enabled:
            return None
        
        try:
            if not DEEPFACE_AVAILABLE or DeepFace is None:
                return None
            
            # Generate face embedding using DeepFace
            embedding = DeepFace.represent(
                face_image,
                model_name=self.model_name,
                enforce_detection=False,
                align=True
            )
            
            # DeepFace returns a list with one dict containing 'embedding'
            if embedding and len(embedding) > 0:
                encoding = np.array(embedding[0]['embedding'])
                logger.debug(f"Generated face encoding with shape: {encoding.shape}")
                return encoding
            else:
                logger.warning("Empty embedding returned from DeepFace")
                return None
                
        except Exception as e:
            logger.warning(f"Face encoding failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    def recognize_face(self, face_image: np.ndarray, database_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Recognize a face by comparing against a database.
        
        Args:
            face_image: Face image as numpy array (RGB format)
            database_path: Path to database of known faces (optional)
            
        Returns:
            Recognition result with identity and confidence, or None
        """
        if not self.enabled:
            return None
        
        if database_path is None:
            # No database provided, just return encoding
            encoding = self.encode_face(face_image)
            if encoding is not None:
                return {
                    "identity": "unknown",
                    "confidence": 0.0,
                    "encoding": encoding.tolist()  # Convert to list for JSON serialization
                }
            return None
        
        try:
            if not DEEPFACE_AVAILABLE or DeepFace is None:
                return None
            
            # Use DeepFace to find identity in database
            result = DeepFace.find(
                face_image,
                db_path=database_path,
                model_name=self.model_name,
                enforce_detection=False,
                silent=True
            )
            
            if result is not None and len(result) > 0 and len(result[0]) > 0:
                # Get the best match
                best_match = result[0].iloc[0]
                identity = best_match['identity']
                distance = best_match['distance']
                
                # Convert distance to confidence (lower distance = higher confidence)
                # This is model-dependent, but a rough conversion
                confidence = max(0.0, 1.0 - (distance / 1.0))  # Normalize distance
                
                return {
                    "identity": identity,
                    "confidence": round(confidence, 3),
                    "distance": round(distance, 4)
                }
            else:
                return {
                    "identity": "unknown",
                    "confidence": 0.0
                }
                
        except Exception as e:
            logger.warning(f"Face recognition failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return None
    
    def analyze_face_quality(self, face_image: np.ndarray) -> Dict[str, Any]:
        """
        Analyze face image quality (blur, brightness, etc.).
        
        Args:
            face_image: Face image as numpy array
            
        Returns:
            Quality metrics dictionary
        """
        try:
            # Convert to grayscale for analysis
            if len(face_image.shape) == 3:
                gray = cv2.cvtColor(face_image, cv2.COLOR_RGB2GRAY)
            else:
                gray = face_image
            
            # Calculate blur score using Laplacian variance
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_score = max(0.0, min(1.0, laplacian_var / 500.0))  # Normalize to 0-1
            
            # Calculate brightness
            brightness = np.mean(gray) / 255.0
            
            # Estimate occlusion (simplified - check for very dark regions)
            dark_pixels = np.sum(gray < 30) / gray.size
            occlusion_estimate = dark_pixels > 0.3  # More than 30% very dark = likely occluded
            
            return {
                "blur_score": round(blur_score, 3),
                "brightness": round(brightness, 3),
                "occlusion": occlusion_estimate,
                "quality_score": round((blur_score + brightness) / 2, 3)
            }
            
        except Exception as e:
            logger.warning(f"Face quality analysis failed: {e}")
            return {
                "blur_score": 0.0,
                "brightness": 0.5,
                "occlusion": False,
                "quality_score": 0.0
            }
    
    def enhance_person_detection_with_faces(self, image: np.ndarray, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance person detections with face recognition data.
        
        Args:
            image: Full image as numpy array (BGR format)
            detections: List of detection dictionaries (person detections will be enhanced)
            
        Returns:
            Enhanced detections with face information
        """
        if not self.enabled:
            return detections
        
        enhanced_detections = []
        
        for detection in detections:
            if detection.get("type") == "person":
                try:
                    bbox_coords = detection.get("bbox_coords", [])
                    if not bbox_coords:
                        # Fallback to bbox if bbox_coords not available
                        bbox = detection.get("bbox", {})
                        if bbox:
                            x = bbox.get("x", 0)
                            y = bbox.get("y", 0)
                            w = bbox.get("w", 0)
                            h = bbox.get("h", 0)
                            bbox_coords = [x, y, x + w, y + h]
                    
                    if not bbox_coords:
                        enhanced_detections.append(detection)
                        continue
                    
                    # Detect faces in person region
                    faces = self.detect_faces(image, bbox_coords)
                    
                    if faces:
                        # Use the first/largest face
                        face = faces[0]
                        face_image = face.get("region")
                        
                        if face_image is not None:
                            # Convert face image to RGB if needed
                            if isinstance(face_image, np.ndarray):
                                if len(face_image.shape) == 3 and face_image.shape[2] == 3:
                                    # Already RGB from DeepFace
                                    pass
                                else:
                                    face_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
                                
                                # Generate face encoding
                                encoding = self.encode_face(face_image)
                                
                                # Analyze face quality
                                quality = self.analyze_face_quality(face_image)
                                
                                # Update detection attributes
                                detection["attributes"]["face"] = {
                                    "present": True,
                                    "encoding_id": f"face_{hash(str(encoding))[:8]}" if encoding is not None else None,
                                    "encoding": encoding.tolist() if encoding is not None else None,
                                    "quality": quality,
                                    "bbox": face.get("bbox")
                                }
                            else:
                                # Face detected but couldn't extract image
                                detection["attributes"]["face"]["present"] = True
                        else:
                            # Face detected but no image extracted
                            detection["attributes"]["face"]["present"] = True
                    else:
                        # No face detected
                        detection["attributes"]["face"]["present"] = False
                    
                except Exception as e:
                    logger.warning(f"Face enhancement failed for detection: {e}")
                    detection["attributes"]["face"]["present"] = False
            
            enhanced_detections.append(detection)
        
        return enhanced_detections
