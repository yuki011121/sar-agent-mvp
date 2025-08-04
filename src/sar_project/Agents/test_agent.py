#!/usr/bin/env python3
"""
Test script for the Interview Analysis Agent
"""

from sar_project.Agents.Interview_agent import InterviewAnalystAgent
import os
from dotenv import load_dotenv
import json

def test_confidence_rating():
    """Test the confidence rating functionality"""
    print("\n=== TESTING CONFIDENCE RATING ===")
    
    # Initialize agent
    agent = InterviewAnalystAgent(
        name="Test Agent",
        role="Test",
        system_message="Test",
        input_text=""
    )
    
    # Test cases
    test_sections = [
        "I definitely saw him at the store yesterday.",
        "I think maybe it was around 3 PM, but I'm not sure.",
        "I absolutely know it was John Smith who was there.",
        "I might have seen something, but I can't remember exactly."
    ]
    
    for section in test_sections:
        result = agent.assign_confidence_rating(section)
        print(f"\nSection: {section}")
        print(f"Confidence Score: {result['confidence_score']}")
        print(f"Confidence Level: {result['confidence_level']}")

def main():
    """Main test function"""
    # Load environment variables
    load_dotenv()
    
    # Check if API key is available
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not found. API features will be disabled.")
    
    # Test confidence rating
    test_confidence_rating()
    
    # Test full analysis
    print("\nStarting interview transcript analysis...")
    transcript_file = '../../../Mock Search 3-8-25 transcription 2.pdf'
    
    if os.path.exists(transcript_file):
        print(f"Analyzing file: {transcript_file}")
        print("-" * 50)
        
        # Initialize agent
        agent = InterviewAnalystAgent(
            name="Interview Analyst Agent",
            role="Interview Transcript Analyst",
            system_message="I am an AI agent specialized in analyzing interview transcripts to identify important information, extract entities, and assess confidence levels in witness statements.",
            input_text=""
        )
        
        # Extract transcript
        text = agent.extract_interview_transcript(transcript_file)
        
        if text:
            # Parse sections
            sections = agent.parse_sections()
            
            # Perform analysis
            confidence_analysis = [agent.assign_confidence_rating(section) for section in sections]
            entity_extraction = agent.extract_entities(sections)
            
            # Use fallback importance scoring since API might not be available
            important_sections = []
            for section in sections:
                important_keywords = ["missing", "saw", "witness", "suspect", "license", "plate", "vehicle", "clothing", "time", "location"]
                section_lower = section.lower()
                score = sum(1 for keyword in important_keywords if keyword in section_lower)
                
                if score >= 2:  # If multiple important keywords found
                    important_sections.append({
                        "section": section,
                        "importance_score": score,
                        "reason": f"Contains {score} important keywords"
                    })
            
            # Generate results
            results = {
                "summary": "Analysis completed with fallback heuristics",
                "total_sections": len(sections),
                "confidence_analysis": confidence_analysis,
                "entity_extraction": entity_extraction,
                "important_sections": important_sections,
                "high_confidence_sections": [s for s in confidence_analysis if s["confidence_level"] == "high"],
                "low_confidence_sections": [s for s in confidence_analysis if s["confidence_level"] == "low"]
            }
            
            # Display results
            print("\n=== ANALYSIS RESULTS ===")
            
            print("\n📋 SUMMARY:")
            print(results.get('summary', 'No summary available'))
            print("=" * 50)
            
            print("\n📊 STATISTICS:")
            print(f"Total sections analyzed: {results['total_sections']}")
            print(f"Important sections found: {len(results['important_sections'])}")
            print(f"High confidence sections: {len(results['high_confidence_sections'])}")
            print(f"Low confidence sections: {len(results['low_confidence_sections'])}")
            print("=" * 50)
            
            if results['important_sections']:
                print("\n🔍 IMPORTANT SECTIONS:")
                for i, section_data in enumerate(results['important_sections'], 1):
                    print(f"\n{i}. Importance Score: {section_data['importance_score']}/10")
                    print(f"   Reason: {section_data['reason']}")
                    print(f"   Content: {section_data['section'][:100]}...")
                print("=" * 50)
            
            if results['entity_extraction']:
                print("\n👥 ENTITY EXTRACTION:")
                for i, entity_data in enumerate(results['entity_extraction'], 1):
                    entities = entity_data['entities']
                    if entities.get('people') or entities.get('places') or entities.get('times'):
                        print(f"\nSection {i}:")
                        if entities.get('people'):
                            print(f"   People: {', '.join(entities['people'])}")
                        if entities.get('places'):
                            print(f"   Places: {', '.join(entities['places'])}")
                        if entities.get('times'):
                            print(f"   Times: {', '.join(entities['times'])}")
                print("=" * 50)
            
            # Save detailed results
            with open('../../../analysis_results.json', 'w') as f:
                json.dump(results, f, indent=2)
            print("\n📄 Detailed results saved to 'analysis_results.json'")
            
        else:
            print("Error: Could not extract text from PDF file")
    else:
        print(f"Error: Transcript file '{transcript_file}' not found")

if __name__ == "__main__":
    main()
