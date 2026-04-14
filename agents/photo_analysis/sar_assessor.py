"""
SAR assessment module for the photo analysis agent.
Handles search and rescue specific analysis and prioritization.
"""

import logging
import traceback
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class SARAssessor:
    """Handles SAR-specific assessment and prioritization."""
    
    def __init__(self):
        """Initialize the SAR assessor."""
        pass
    
    def calculate_search_priority(self, detections: List[Dict[str, Any]], person_analysis: Dict[str, Any]) -> str:
        """Calculate search priority based on SAR-relevant factors."""
        try:
            priority_score = 0
            
            # Check for people (highest priority)
            people_count = person_analysis.get("total_people", 0)
            if people_count > 0:
                priority_score += 100 * people_count
            
            # Check for vehicles/boats (potential rescue resources)
            vehicles = [d for d in detections if d.get("type") in ["car", "truck", "boat", "motorcycle"]]
            if vehicles:
                priority_score += 30 * len(vehicles)
            
            # Check for water bodies (high risk)
            water_indicators = [d for d in detections if d.get("type") in ["boat", "water"]]
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
    
    def assess_accessibility(self, detections: List[Dict[str, Any]], image_path: str) -> Dict[str, Any]:
        """Assess terrain accessibility for SAR operations."""
        try:
            accessibility_score = 100  # Start with perfect accessibility
            
            # Check for terrain obstacles
            obstacles = [d for d in detections if d.get("type") in ["tree", "rock", "cliff", "mountain"]]
            if obstacles:
                accessibility_score -= 20 * len(obstacles)
            
            # Check for water bodies (may require boats)
            water_bodies = [d for d in detections if d.get("type") in ["boat", "water"]]
            if water_bodies:
                accessibility_score -= 30
            
            # Check for vehicles (good for access)
            vehicles = [d for d in detections if d.get("type") in ["car", "truck", "motorcycle"]]
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
    
    def determine_urgency_level(self, detections: List[Dict[str, Any]], person_analysis: Dict[str, Any]) -> str:
        """Determine urgency level for SAR response."""
        try:
            urgency_factors = []
            
            # People detected (highest urgency)
            people_count = person_analysis.get("total_people", 0)
            if people_count > 0:
                urgency_factors.append(f"{people_count} person(s) detected")
            
            # Water presence (high risk)
            water_indicators = [d for d in detections if d.get("type") in ["boat", "water"]]
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
    
    def analyze_weather_conditions(self, image_path: str) -> Dict[str, Any]:
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
    
    def calculate_sar_metadata(self, detections: List[Dict[str, Any]], person_analysis: Dict[str, Any], image_path: str) -> Dict[str, Any]:
        """Calculate comprehensive SAR-specific metadata."""
        try:
            # Calculate all SAR metrics
            search_priority = self.calculate_search_priority(detections, person_analysis)
            accessibility = self.assess_accessibility(detections, image_path)
            urgency_level = self.determine_urgency_level(detections, person_analysis)
            weather_conditions = self.analyze_weather_conditions(image_path)
            
            return {
                "search_priority": search_priority,
                "accessibility": accessibility,
                "urgency_level": urgency_level,
                "weather_conditions": weather_conditions,
                "sar_metrics": {
                    "people_count": person_analysis.get("total_people", 0),
                    "vehicle_count": len([d for d in detections if d.get("type") in ["car", "truck", "boat", "motorcycle"]]),
                    "terrain_complexity": "HIGH" if accessibility["level"] in ["DIFFICULT", "VERY_DIFFICULT"] else "LOW"
                }
            }
            
        except Exception as e:
            logger.error(f"SAR metadata calculation failed: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "search_priority": "UNKNOWN",
                "accessibility": {"score": 50, "level": "UNKNOWN"},
                "urgency_level": "UNKNOWN",
                "weather_conditions": {"visibility": "UNKNOWN", "lighting": "UNKNOWN"},
                "sar_metrics": {"people_count": 0, "vehicle_count": 0, "terrain_complexity": "UNKNOWN"}
            }
    
    def create_sar_assessment(self, sar_metadata: Dict[str, Any], detections: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create SAR assessment section with priority, urgency, accessibility, and weather."""
        try:
            # Map priority levels to scores
            priority_scores = {
                "CRITICAL": 0.95,
                "HIGH": 0.8,
                "MEDIUM": 0.6,
                "LOW": 0.3,
                "UNKNOWN": 0.1
            }
            
            priority_label = sar_metadata.get("search_priority", "UNKNOWN")
            priority_score = priority_scores.get(priority_label, 0.1)
            
            # Create accessibility mapping
            accessibility_level = sar_metadata.get("accessibility", {}).get("level", "UNKNOWN")
            terrain_mapping = {
                "EASY": "LOW_COMPLEXITY",
                "MODERATE": "MEDIUM_COMPLEXITY", 
                "DIFFICULT": "HIGH_COMPLEXITY",
                "VERY_DIFFICULT": "HIGH_COMPLEXITY",
                "UNKNOWN": "UNKNOWN"
            }
            
            # Create weather mapping
            weather = sar_metadata.get("weather_conditions", {})
            visibility_mapping = {
                "GOOD": 2000,
                "POOR": 500,
                "UNKNOWN": 1000
            }
            
            lighting_mapping = {
                "DAY": "GOOD",
                "NIGHT": "LOW", 
                "UNKNOWN": "UNKNOWN"
            }
            
            # Create risk factors
            risk_factors = []
            people_count = sar_metadata.get("sar_metrics", {}).get("people_count", 0)
            if people_count > 0:
                risk_factors.append({
                    "name": "multiple_persons",
                    "weight": 0.4,
                    "contrib": min(0.4 * (people_count / 3), 0.4)
                })
            
            water_present = sar_metadata.get("accessibility", {}).get("water_present", False)
            if water_present:
                risk_factors.append({
                    "name": "water_presence", 
                    "weight": 0.35,
                    "contrib": 0.35
                })
            
            lighting = weather.get("lighting", "UNKNOWN")
            if lighting == "NIGHT":
                risk_factors.append({
                    "name": "low_visibility",
                    "weight": 0.25,
                    "contrib": 0.25
                })
            
            # Create explanation
            explanation_parts = []
            if people_count > 0:
                explanation_parts.append(f"{people_count} person(s) detected")
            if water_present:
                explanation_parts.append("water presence")
            if lighting == "NIGHT":
                explanation_parts.append("low visibility")
            
            explanation = "; ".join(explanation_parts) + "." if explanation_parts else "No significant risk factors detected."
            
            return {
                "priority": {
                    "label": priority_label,
                    "score": priority_score
                },
                "urgency": sar_metadata.get("urgency_level", "UNKNOWN"),
                "accessibility": {
                    "terrain": terrain_mapping.get(accessibility_level, "UNKNOWN"),
                    "vehicle_access": "GOOD" if sar_metadata.get("accessibility", {}).get("vehicle_access", False) else "LIMITED",
                    "water_presence": water_present,
                    "obstacles": ["dense_vegetation"] if accessibility_level in ["DIFFICULT", "VERY_DIFFICULT"] else []
                },
                "weather": {
                    "visibility_m": visibility_mapping.get(weather.get("visibility", "UNKNOWN"), 1000),
                    "lighting": lighting_mapping.get(lighting, "UNKNOWN"),
                    "conditions": [] if weather.get("weather_conditions") == "UNKNOWN" else [weather.get("weather_conditions", "unknown")]
                },
                "equipment_detected": [],  # No emergency equipment detection
                "risk_factors": risk_factors,
                "explanation": explanation
            }
            
        except Exception as e:
            logger.error(f"SAR assessment creation failed: {e}")
            return {
                "priority": {"label": "UNKNOWN", "score": 0.1},
                "urgency": "UNKNOWN",
                "accessibility": {"terrain": "UNKNOWN", "vehicle_access": "UNKNOWN", "water_presence": False, "obstacles": []},
                "weather": {"visibility_m": 1000, "lighting": "UNKNOWN", "conditions": []},
                "equipment_detected": [],
                "risk_factors": [],
                "explanation": "Assessment failed"
            }
