#!/usr/bin/env python3
"""
Example usage of the Interview Analysis Agent
"""

from Interview_agent import InterviewAnalystAgent
import os
from dotenv import load_dotenv
import json

def example_basic_analysis():
    """Example of basic transcript analysis"""
    print("🔍 Example: Basic Transcript Analysis")
    print("=" * 50)
    
    # Initialize agent
    agent = InterviewAnalystAgent(
        name="Interview Analyst",
        role="Transcript Analysis",
        system_message="Specialized in analyzing interview transcripts for missing persons cases"
    )
    
    # Analyze the sample transcript
    transcript_file = 'Mock Search 3-8-25 transcription 2.pdf'
    
    if os.path.exists(transcript_file):
        print(f"Analyzing: {transcript_file}")
        results = agent.analyze_transcript(transcript_file)
        
        if "error" not in results:
            print(f"\n📊 Analysis Results:")
            print(f"   Total sections: {results['total_sections']}")
            print(f"   Important sections: {len(results['important_sections'])}")
            print(f"   High confidence sections: {len(results['high_confidence_sections'])}")
            
            # Show summary if available
            if results.get('summary'):
                print(f"\n📋 Summary:")
                print(results['summary'][:500] + "...")
        else:
            print(f"Error: {results['error']}")
    else:
        print(f"Transcript file not found: {transcript_file}")

def example_confidence_analysis():
    """Example of confidence analysis on sample text"""
    print("\n📊 Example: Confidence Analysis")
    print("=" * 50)
    
    agent = InterviewAnalystAgent(
        name="Confidence Analyzer",
        role="Confidence Assessment",
        system_message="Analyzing witness confidence levels"
    )
    
    # Sample interview sections with different confidence levels
    sample_sections = [
        "I definitely saw John at the store around 3 PM yesterday. I'm absolutely certain it was him.",
        "I think I might have seen someone who looked like John, but I'm not really sure.",
        "I believe it was probably around 3 PM, but I can't remember exactly.",
        "I know for sure that John was wearing a red jacket and blue jeans."
    ]
    
    for i, section in enumerate(sample_sections, 1):
        result = agent.assign_confidence_rating(section)
        print(f"\n{i}. Section: {section[:50]}...")
        print(f"   Confidence Score: {result['confidence_score']}")
        print(f"   Confidence Level: {result['confidence_level']}")

def example_entity_extraction():
    """Example of entity extraction"""
    print("\n👥 Example: Entity Extraction")
    print("=" * 50)
    
    agent = InterviewAnalystAgent(
        name="Entity Extractor",
        role="Entity Extraction",
        system_message="Extracting people, places, and times from interview text"
    )
    
    # Sample interview text
    sample_text = """
    I saw John Smith at the downtown mall on March 15th around 3:30 PM. 
    He was talking to Jane Doe near the food court. 
    I remember it was a Tuesday afternoon, and the weather was cloudy.
    """
    
    agent.input_text = sample_text
    sections = agent.parse_sections()
    
    if sections:
        entities = agent.extract_entities(sections)
        for i, entity_data in enumerate(entities, 1):
            print(f"\nSection {i} Entities:")
            entities_dict = entity_data['entities']
            
            if entities_dict.get('people'):
                print(f"   People: {', '.join(entities_dict['people'])}")
            if entities_dict.get('places'):
                print(f"   Places: {', '.join(entities_dict['places'])}")
            if entities_dict.get('times'):
                print(f"   Times: {', '.join(entities_dict['times'])}")

def example_importance_scoring():
    """Example of importance scoring"""
    print("\n⭐ Example: Importance Scoring")
    print("=" * 50)
    
    agent = InterviewAnalystAgent(
        name="Importance Scorer",
        role="Importance Assessment",
        system_message="Identifying important information in interview transcripts"
    )
    
    # Sample interview sections with varying importance
    sample_sections = [
        "The missing person was last seen wearing a red jacket and blue jeans.",
        "I think I might have seen something, but I'm not sure.",
        "The suspect was driving a white van with license plate ABC-123.",
        "The weather was nice that day, and I had a good lunch."
    ]
    
    for i, section in enumerate(sample_sections, 1):
        print(f"\n{i}. Section: {section}")
        # Note: This would require API calls, so we'll just show the structure
        print(f"   [Importance analysis would be performed here with API]")

def example_custom_analysis():
    """Example of custom analysis workflow"""
    print("\n🔧 Example: Custom Analysis Workflow")
    print("=" * 50)
    
    agent = InterviewAnalystAgent(
        name="Custom Analyzer",
        role="Custom Analysis",
        system_message="Performing custom analysis on interview data"
    )
    
    # Custom workflow
    transcript_file = 'Mock Search 3-8-25 transcription 2.pdf'
    
    if os.path.exists(transcript_file):
        # Step 1: Extract transcript
        print("Step 1: Extracting transcript...")
        text = agent.extract_interview_transcript(transcript_file)
        
        if text:
            print(f"   ✅ Extracted {len(text)} characters")
            
            # Step 2: Parse sections
            print("\nStep 2: Parsing sections...")
            sections = agent.parse_sections()
            print(f"   ✅ Found {len(sections)} sections")
            
            # Step 3: Analyze confidence
            print("\nStep 3: Analyzing confidence levels...")
            confidence_results = [agent.assign_confidence_rating(section) for section in sections[:3]]  # Limit for demo
            
            for i, result in enumerate(confidence_results, 1):
                print(f"   Section {i}: {result['confidence_level']} confidence (score: {result['confidence_score']})")
            
            # Step 4: Save results
            print("\nStep 4: Saving results...")
            results = {
                "transcript_length": len(text),
                "total_sections": len(sections),
                "confidence_analysis": confidence_results
            }
            
            with open('custom_analysis_results.json', 'w') as f:
                json.dump(results, f, indent=2)
            print("   ✅ Results saved to 'custom_analysis_results.json'")
        else:
            print("   ❌ Failed to extract transcript")
    else:
        print(f"   ❌ Transcript file not found: {transcript_file}")

def main():
    """Run all examples"""
    print("🚀 Interview Analysis Agent - Examples")
    print("=" * 60)
    
    # Load environment
    load_dotenv()
    
    # Check if API key is available
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not found. Some features will be limited.")
        print("   Create a .env file with your OPENAI_API_KEY for full functionality.\n")
    
    # Run examples
    example_confidence_analysis()
    example_entity_extraction()
    example_importance_scoring()
    example_custom_analysis()
    
    # Only run full analysis if API key is available
    if os.getenv("OPENAI_API_KEY"):
        example_basic_analysis()
    else:
        print("\n🔒 Full analysis example skipped - API key required")
    
    print("\n" + "=" * 60)
    print("✅ Examples completed!")
    print("\n📋 To run full analysis with API:")
    print("   1. Create .env file with OPENAI_API_KEY")
    print("   2. Run: python test_agent.py")

if __name__ == "__main__":
    main() 