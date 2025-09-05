#!/usr/bin/env python3
"""
Interview Analysis Agent - Standalone version without AutoGen dependency
"""

import openai
import os
import json
from PyPDF2 import PdfReader
from dotenv import load_dotenv

class InterviewAnalystAgent:
    def __init__(self, name, role, system_message, input_text=""):
        self.name = name
        self.role = role
        self.system_message = system_message
        self.input_text = input_text
        
        # Load environment variables
        load_dotenv()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Configure OpenAI
        if self.openai_api_key:
            openai.api_key = self.openai_api_key

    def extract_interview_transcript(self, filename):
        """Extract text from PDF file"""
        try:
            reader = PdfReader(filename)
            text = ''
            for page in reader.pages:
                text += page.extract_text()
            
            self.input_text = text
            print(f"Successfully extracted {len(text)} characters from PDF")
            return text
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return None

    def ask_chatgpt(self, prompt):
        """Ask ChatGPT a question"""
        if not self.openai_api_key:
            print("Warning: No OpenAI API key found. Using fallback heuristics.")
            return None
            
        try:
            response = openai.OpenAI().chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return None

    def assign_confidence_rating(self, section: str):
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

    def extract_entities(self, sections):
        """Extract entities (people, places, times) from sections"""
        extracted_data = []
        
        for section in sections:
            prompt = (
                "Extract the names of people, places, and time references from the following interview section. "
                "Respond in JSON format with keys: people, places, times.\n\n"
                f"{section}"
            )
            
            response = self.ask_chatgpt(prompt)
            
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

    def _extract_entities_heuristic(self, section):
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

    def identify_important_sections(self, sections):
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
            
            response = self.ask_chatgpt(prompt)
            
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

    def _calculate_importance_heuristic(self, section):
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

    def parse_sections(self):
        """Parse input text into logical sections"""
        if not self.input_text:
            return []
        
        # Split by double line breaks or periods followed by space and capital letter
        sections = []
        raw_sections = self.input_text.split('\n\n')
        
        for section in raw_sections:
            # Further split by sentence boundaries
            sentences = section.split('. ')
            for sentence in sentences:
                cleaned = sentence.strip()
                if cleaned and len(cleaned) > 10:  # Only include substantial sections
                    sections.append(cleaned)
        
        return sections

    def analyze_transcript(self, filename):
        """Complete transcript analysis workflow"""
        # Extract transcript
        text = self.extract_interview_transcript(filename)
        if not text:
            return {"error": "Could not extract text from PDF"}
        
        # Parse sections
        sections = self.parse_sections()
        
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
            "low_confidence_sections": [s for s in confidence_analysis if s["confidence_level"] == "low"]
        }
        
        return results

    def process_request(self, request_type, **kwargs):
        """Process different types of analysis requests"""
        if request_type == "confidence":
            return self.assign_confidence_rating(kwargs.get("text", ""))
        elif request_type == "entities":
            return self.extract_entities(kwargs.get("sections", []))
        elif request_type == "importance":
            return self.identify_important_sections(kwargs.get("sections", []))
        elif request_type == "full_analysis":
            return self.analyze_transcript(kwargs.get("filename", ""))
        else:
            return {"error": f"Unknown request type: {request_type}"}

if __name__ == "__main__":
    pdf_path = "data/transcripts/Mock Search 3-8-25 transcription 2.pdf"

    print(f"--- Initializing Interview Analyst Agent ---")
    analyst = InterviewAnalystAgent(
        name="Interview Analyst",
        role="To analyze interview transcripts for key clues.",
        system_message="You are an AI assistant that extracts key information from interview transcripts."
    )

    print(f"\n--- Starting Full Analysis of {pdf_path} ---")
    results = analyst.analyze_transcript(pdf_path)

    output_path = "interview_analysis_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)

    print(f"\n--- Analysis Complete ---")
    print(f"Results saved to: {output_path}")


















