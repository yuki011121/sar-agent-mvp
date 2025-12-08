"""
Color analysis module for the photo analysis agent.
Handles hair and clothing color analysis using computer vision techniques.
"""

import logging
import traceback
from typing import List, Optional, Dict
import cv2
import numpy as np

logger = logging.getLogger(__name__)

class ColorAnalyzer:
    """Handles color analysis for hair and clothing detection."""
    
    def __init__(self):
        """Initialize the color analyzer."""
        pass
    
    def detect_skin_region(self, image: np.ndarray, bbox: List[float]) -> Optional[List[int]]:
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
    
    def get_dominant_color_clustered(self, image: np.ndarray, bbox: List[float], num_clusters: int = 3) -> str:
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
    
    def analyze_hair_color(self, image: np.ndarray, bbox: List[float]) -> str:
        """Analyze hair color with improved region detection."""
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            # Detect skin region to find face
            face_region = self.detect_skin_region(image, bbox)
            
            if face_region:
                # If we found a face, analyze the region above it for hair
                fx1, fy1, fx2, fy2 = face_region
                hair_bbox = [x1, y1, x2, fy1]  # Region above face
            else:
                # Fallback to upper 1/4 if no face detected
                hair_region_height = int((y2 - y1) * 0.25)
                hair_bbox = [x1, y1, x2, y1 + hair_region_height]
            
            hair_color = self.get_dominant_color_clustered(image, hair_bbox)
            
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
            logger.warning(f"Hair color analysis failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return "unknown"
    
    def analyze_clothing_color(self, image: np.ndarray, bbox: List[float]) -> str:
        """Analyze clothing color with improved region detection."""
        try:
            x1, y1, x2, y2 = map(int, bbox)
            
            # Detect skin region to find face
            face_region = self.detect_skin_region(image, bbox)
            
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
            
            clothing_color = self.get_dominant_color_clustered(image, clothing_bbox)
            
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
            logger.warning(f"Clothing color analysis failed: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return "unknown"
    
    def enhance_person_detection(self, image: np.ndarray, detections: List[Dict]) -> List[Dict]:
        """Enhance person detections with color analysis."""
        enhanced_detections = []
        
        for detection in detections:
            if detection.get("type") == "person":
                try:
                    # Analyze hair color
                    hair_color = self.analyze_hair_color(image, detection.get("bbox_coords", []))
                    detection["attributes"]["appearance"]["hair_color"] = hair_color
                except Exception as e:
                    logger.warning(f"Hair color analysis failed: {e}")
                    detection["attributes"]["appearance"]["hair_color"] = "unknown"
                
                try:
                    # Analyze clothing color
                    clothing_color = self.analyze_clothing_color(image, detection.get("bbox_coords", []))
                    detection["attributes"]["appearance"]["clothing_colors"] = [clothing_color]
                except Exception as e:
                    logger.warning(f"Clothing color analysis failed: {e}")
                    detection["attributes"]["appearance"]["clothing_colors"] = ["unknown"]
            
            enhanced_detections.append(detection)
        
        return enhanced_detections
