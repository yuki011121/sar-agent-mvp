#!/usr/bin/env python3
"""
Interview Analysis Agent - Integrated with Redis and MCP A2A system
"""

import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
import requests
from PyPDF2 import PdfReader
from dotenv import load_dotenv

from shared import RedisBus, wrap_envelope, parse_message_from_stream, mcp_tools

# Load environment variables
load_dotenv()

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 30))  # Check every 30 seconds
AGENT_NAME = "interview-agent"
AGENT_VERSION = "interview-agent-v1.0"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Redis stream names
INTERVIEW_INPUT_STREAM = "interview.in.raw"
INTERVIEW_OUTPUT_STREAM = "interview.analysis.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


def download_pdf_from_url(url: str) -> Optional[bytes]:
    """
    Download PDF from URL (supports MinIO presigned URLs and HTTP URLs).
    Returns the PDF content as bytes.
    """
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        logger.info(f"Downloaded PDF from URL ({len(response.content)} bytes)")
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download PDF from URL {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading PDF: {e}")
        return None


class InterviewAnalystAgent:
    def __init__(self):
        self.name = AGENT_NAME
        self.version = AGENT_VERSION
        self.google_api_key = GOOGLE_API_KEY
        
        # Initialize Gemini if API key is available
        if self.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.google_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.gemini_model = None
        else:
            logger.warning("No Google API key found. Using fallback heuristics.")
            self.gemini_model = None

    def extract_interview_transcript(self, pdf_content: bytes) -> Optional[str]:
        """Extract text from PDF content"""
        try:
            import io
            from PyPDF2 import PdfReader
            
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)
            text = ''
            for page in reader.pages:
                text += page.extract_text()
            
            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return None

    def ask_llm(self, prompt: str) -> Optional[str]:
        """Ask LLM a question using Gemini or fallback"""
        if not self.gemini_model:
            logger.warning("No Gemini client available. Using fallback.")
            return None
            
        try:
            system_prompt = "You are a helpful assistant for analyzing interview transcripts in search and rescue operations."
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
            
            response = self.gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 1000,
                }
            )
            return response.text
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None

    def assign_confidence_rating(self, section: str) -> Dict[str, Any]:
        """Assign confidence rating to a section of text"""
        confidence_indicators = {
            "low": ["think", "maybe", "might", "unsure", "not sure", "can't remember", "sort of", "i guess", "possibly", "perhaps"],
            "medium": ["probably", "presumably", "i believe", "i assume", "around", "about", "seems like"],
            "high": ["definitely", "absolutely", "exactly", "certainly", "for sure", "no doubt", "i saw", "i know", "clearly", "obviously"]
        }
        
        confidence_score = 0
        section_lower = section.lower()
        
        for level, indicators in confidence_indicators.items():
            for indicator in indicators:
                if indicator in section_lower:
                    if level == "low":
                        confidence_score += 1
                    elif level == "medium":
                        confidence_score += 2
                    elif level == "high":
                        confidence_score += 3
        
        # Determine confidence level
        if confidence_score >= 6:
            confidence_level = "high"
        elif confidence_score >= 3:
            confidence_level = "medium"
        else:
            confidence_level = "low"
        
        return {
            "section": section,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level
        }

    def extract_entities(self, sections: List[str]) -> List[Dict[str, Any]]:
        """Extract entities (people, places, times) from sections"""
        extracted_data = []
        
        for section in sections:
            prompt = (
                "Extract the names of people, places, and time references from the following interview section. "
                "Respond in JSON format with keys: people, places, times.\n\n"
                f"{section}"
            )
            
            response = self.ask_llm(prompt)
            
            if response:
                try:
                    entities = json.loads(response)
                except json.JSONDecodeError:
                    entities = {"people": [], "places": [], "times": []}
            else:
                # Fallback: simple heuristic extraction
                entities = self._extract_entities_heuristic(section)
            
            extracted_data.append({
                "section": section,
                "entities": entities
            })
        
        return extracted_data

    def _extract_entities_heuristic(self, section: str) -> Dict[str, List[str]]:
        """Fallback heuristic for entity extraction"""
        entities = {"people": [], "places": [], "times": []}
        
        # Simple heuristics for entity extraction
        words = section.split()
        for word in words:
            # Remove punctuation
            clean_word = word.strip(".,!?;:")
            
            # Check for time patterns
            if any(time_word in clean_word.lower() for time_word in ["am", "pm", "o'clock", "morning", "afternoon", "evening", "night"]):
                entities["times"].append(clean_word)
            
            # Check for potential names (capitalized words that aren't at sentence start)
            if clean_word and clean_word[0].isupper() and len(clean_word) > 2:
                entities["people"].append(clean_word)
        
        return entities

    def identify_important_sections(self, sections: List[str]) -> List[Dict[str, Any]]:
        """Identify important sections using LLM or heuristics"""
        important_sections = []
        
        for section in sections:
            prompt = (
                "Rate the importance of this interview section on a scale of 1-10, "
                "where 10 is extremely important. Consider factors like:\n"
                "- Direct witness observations\n"
                "- Specific details about missing persons\n"
                "- Vehicle or license plate information\n"
                "- Time and location details\n"
                "- Physical descriptions\n\n"
                f"Section: {section}\n\n"
                "Respond with just the number (1-10):"
            )
            
            response = self.ask_llm(prompt)
            
            if response:
                try:
                    importance_score = int(response.strip())
                except ValueError:
                    importance_score = self._calculate_importance_heuristic(section)
            else:
                importance_score = self._calculate_importance_heuristic(section)
            
            if importance_score >= 7:
                important_sections.append({
                    "section": section,
                    "importance_score": importance_score,
                    "reason": f"Rated {importance_score}/10 for importance"
                })
        
        return important_sections

    def _calculate_importance_heuristic(self, section: str) -> int:
        """Fallback heuristic for importance scoring"""
        important_keywords = [
            "missing", "saw", "witness", "suspect", "license", "plate", 
            "vehicle", "car", "truck", "clothing", "time", "location", 
            "address", "phone", "number", "description", "height", "weight",
            "hair", "eyes", "tattoo", "scar", "birthmark"
        ]
        
        section_lower = section.lower()
        score = sum(1 for keyword in important_keywords if keyword in section_lower)
        
        # Normalize to 1-10 scale
        return min(score * 2, 10)

    def parse_sections(self, text: str) -> List[str]:
        """Parse input text into logical sections"""
        if not text:
            return []
        
        # Split by double line breaks or periods followed by space and capital letter
        sections = []
        raw_sections = text.split('\n\n')
        
        for section in raw_sections:
            # Further split by sentence boundaries
            sentences = section.split('. ')
            for sentence in sentences:
                cleaned = sentence.strip()
                if cleaned and len(cleaned) > 10:  # Only include substantial sections
                    sections.append(cleaned)
        
        return sections

    def analyze_transcript(self, transcript_text: str) -> Dict[str, Any]:
        """Complete transcript analysis workflow"""
        if not transcript_text:
            return {"error": "No transcript text provided"}
        
        # Parse sections
        sections = self.parse_sections(transcript_text)
        
        # Perform analysis
        confidence_analysis = [self.assign_confidence_rating(section) for section in sections]
        entity_extraction = self.extract_entities(sections)
        important_sections = self.identify_important_sections(sections)
        
        # Compile results
        results = {
            "summary": f"Analyzed {len(sections)} sections from transcript",
            "total_sections": len(sections),
            "confidence_analysis": confidence_analysis,
            "entity_extraction": entity_extraction,
            "important_sections": important_sections,
            "high_confidence_sections": [s for s in confidence_analysis if s["confidence_level"] == "high"],
            "low_confidence_sections": [s for s in confidence_analysis if s["confidence_level"] == "low"],
            "analysis_timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        return results

    def process_interview_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process interview analysis request"""
        try:
            # Extract transcript data - support file_url, pdf_content, or transcript_text
            if request_data.get("file_url"):
                # Handle MinIO presigned URL - download and extract
                file_url = request_data["file_url"]
                logger.info(f"Downloading PDF from URL: {file_url[:100]}...")
                pdf_content = download_pdf_from_url(file_url)
                if not pdf_content:
                    return {"error": f"Failed to download PDF from URL: {file_url}"}
                transcript_text = self.extract_interview_transcript(pdf_content)
            elif "pdf_content" in request_data:
                # Handle PDF content (base64 encoded)
                pdf_content = request_data["pdf_content"]
                if isinstance(pdf_content, str):
                    # Base64 encoded PDF
                    import base64
                    pdf_content = base64.b64decode(pdf_content)
                transcript_text = self.extract_interview_transcript(pdf_content)
            elif "transcript_text" in request_data:
                # Handle plain text
                transcript_text = request_data["transcript_text"]
            else:
                return {"error": "No transcript data provided (file_url, pdf_content, or transcript_text required)"}
            
            if not transcript_text:
                return {"error": "Failed to extract transcript text"}
            
            # Perform analysis
            analysis_result = self.analyze_transcript(transcript_text)
            
            return {
                "status": "success",
                "analysis": analysis_result,
                "metadata": {
                    "agent_name": self.name,
                    "agent_version": self.version,
                    "processed_at": datetime.utcnow().isoformat() + "Z"
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing interview request: {e}")
            return {
                "status": "error",
                "error": str(e),
                "metadata": {
                    "agent_name": self.name,
                    "agent_version": self.version,
                    "processed_at": datetime.utcnow().isoformat() + "Z"
                }
            }

def main():
    """Main function for the Interview Analysis Agent"""
    logger.info(f"Initializing {AGENT_NAME}...")
    
    # Initialize Redis connection
    try:
        bus = RedisBus(REDIS_URL)
        logger.info(f"Successfully connected to Redis at {REDIS_URL}")
    except Exception as e:
        logger.critical(f"Failed to connect to Redis: {e}")
        return
    
    # Initialize the interview analyst
    analyst = InterviewAnalystAgent()
    
    logger.info(f"{AGENT_NAME} starting up. Listening on stream: {INTERVIEW_INPUT_STREAM}")
    logger.info(f"Update interval: {UPDATE_INTERVAL_SECONDS} seconds")
    
    # Main processing loop using subscribe
    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-group",
            consumer_name=f"{AGENT_NAME}-consumer",
            streams=[INTERVIEW_INPUT_STREAM],
            block_ms=UPDATE_INTERVAL_SECONDS * 1000
        ):
            try:
                # Extract payload from StandardMessage object
                payload = message.payload
                logger.info(f"Processing interview request from message {message.envelope.message_id}")
                
                # Extract task_id for correlation (from dispatch tool)
                task_id = payload.pop("task_id", None)
                
                # Process the interview request
                result = analyst.process_interview_request(payload)
                
                # Include task_id in response for correlation
                if task_id:
                    result["task_id"] = task_id
                
                # Publish result to output stream
                output_message = wrap_envelope(
                    payload=result,
                    source_name=AGENT_NAME,
                    source_version=AGENT_VERSION,
                    target_stream=INTERVIEW_OUTPUT_STREAM
                )
                
                bus.publish(output_message)
                logger.info(f"Published interview analysis result to {INTERVIEW_OUTPUT_STREAM}" +
                           (f" (task_id: {task_id})" if task_id else ""))
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
                # Send error to dead letter stream
                error_payload = {
                    "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
                    "error_message": str(e),
                    "error_type": type(e).__name__,
                    "context": "Failed while processing interview analysis request"
                }
                
                error_message = wrap_envelope(
                    payload=error_payload,
                    source_name=AGENT_NAME,
                    source_version=AGENT_VERSION,
                    target_stream=DEAD_LETTER_STREAM
                )
                
                bus.publish(error_message)
                logger.error(f"Sent error to dead letter stream: {DEAD_LETTER_STREAM}")
                
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down gracefully")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}")
        time.sleep(UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()