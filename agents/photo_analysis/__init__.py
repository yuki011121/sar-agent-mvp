"""
Photo Analysis Agent Package

A modular photo analysis agent for search and rescue operations.
Uses YOLOv8 for object detection and computer vision for color analysis.
"""

from .main import PhotoAnalysisAgent, main
from .image_analyzer import ImageAnalyzer
from .color_analyzer import ColorAnalyzer
from .sar_assessor import SARAssessor
from .output_formatter import OutputFormatter
from .redis_client import RedisClient
from .face_recognition import FaceRecognizer

__version__ = "1.0.0"
__author__ = "SAR Agent Team"

__all__ = [
    "PhotoAnalysisAgent",
    "main",
    "ImageAnalyzer", 
    "ColorAnalyzer",
    "SARAssessor",
    "OutputFormatter",
    "RedisClient",
    "FaceRecognizer"
]