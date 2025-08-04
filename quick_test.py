#!/usr/bin/env python3
"""
Quick test script to verify basic functionality without API calls
"""

import os
from Interview_agent import InterviewAnalystAgent

def test_basic_functionality():
    """Test basic agent functionality without API calls"""
    print("🧪 Testing Basic Functionality")
    print("=" * 40)
    
    # Test agent initialization
    try:
        agent = InterviewAnalystAgent(
            name="Test Agent",
            role="Test",
            system_message="Test",
            input_text=""
        )
        print("✅ Agent initialization successful")
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        return False
    
    # Test confidence rating
    test_sections = [
        "I definitely saw him at the store yesterday.",
        "I think maybe it was around 3 PM, but I'm not sure.",
        "I absolutely know it was John Smith who was there.",
        "I might have seen something, but I can't remember exactly."
    ]
    
    print("\n📊 Testing Confidence Rating:")
    for i, section in enumerate(test_sections, 1):
        try:
            result = agent.assign_confidence_rating(section)
            print(f"   {i}. Score: {result['confidence_score']}, Level: {result['confidence_level']}")
        except Exception as e:
            print(f"   {i}. ❌ Error: {e}")
    
    # Test PDF extraction (if file exists)
    pdf_file = 'Mock Search 3-8-25 transcription 2.pdf'
    if os.path.exists(pdf_file):
        print(f"\n📄 Testing PDF Extraction:")
        try:
            text = agent.extract_interview_transcript(pdf_file)
            if text:
                print(f"   ✅ Successfully extracted {len(text)} characters")
                print(f"   📝 Preview: {text[:100]}...")
            else:
                print("   ❌ No text extracted")
        except Exception as e:
            print(f"   ❌ PDF extraction failed: {e}")
    else:
        print(f"\n📄 PDF file '{pdf_file}' not found - skipping PDF test")
    
    # Test section parsing
    print(f"\n🔍 Testing Section Parsing:")
    test_text = "This is section one.\n\nThis is section two.\n\nThis is section three."
    agent.input_text = test_text
    sections = agent.parse_sections()
    print(f"   ✅ Parsed {len(sections)} sections")
    
    print("\n✅ Basic functionality tests completed!")
    return True

def check_dependencies():
    """Check if required dependencies are installed"""
    print("📦 Checking Dependencies")
    print("=" * 40)
    
    dependencies = [
        ('openai', 'OpenAI API client'),
        ('PyPDF2', 'PDF text extraction'),
        ('dotenv', 'Environment variable management'),
    ]
    
    all_good = True
    for module, description in dependencies:
        try:
            __import__(module)
            print(f"   ✅ {module} ({description})")
        except ImportError:
            print(f"   ❌ {module} ({description}) - NOT INSTALLED")
            all_good = False
    
    return all_good

def check_environment():
    """Check environment setup"""
    print("\n🔧 Checking Environment")
    print("=" * 40)
    
    # Check for .env file
    if os.path.exists('.env'):
        print("   ✅ .env file found")
    else:
        print("   ⚠️  .env file not found - create one with your OPENAI_API_KEY")
    
    # Check for API key
    from dotenv import load_dotenv
    load_dotenv()
    
    if os.getenv("OPENAI_API_KEY"):
        print("   ✅ OPENAI_API_KEY found in environment")
    else:
        print("   ❌ OPENAI_API_KEY not found - add it to your .env file")
    
    # Check for PDF file
    pdf_file = 'Mock Search 3-8-25 transcription 2.pdf'
    if os.path.exists(pdf_file):
        print(f"   ✅ Sample PDF file found: {pdf_file}")
    else:
        print(f"   ⚠️  Sample PDF file not found: {pdf_file}")

def main():
    """Run all tests"""
    print("🚀 Interview Agent Quick Test")
    print("=" * 50)
    
    # Check dependencies
    deps_ok = check_dependencies()
    
    # Check environment
    check_environment()
    
    # Test basic functionality
    if deps_ok:
        test_basic_functionality()
    else:
        print("\n❌ Please install missing dependencies before running tests")
        print("   Run: pip install -r requirements.txt")
    
    print("\n" + "=" * 50)
    print("📋 Next Steps:")
    print("   1. Install dependencies: pip install -r requirements.txt")
    print("   2. Create .env file with your OPENAI_API_KEY")
    print("   3. Run full test: python test_agent.py")
    print("   4. Check README.md for detailed usage instructions")

if __name__ == "__main__":
    main() 