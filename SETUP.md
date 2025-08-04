# Interview Analysis Agent - Setup Guide

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
Create a `.env` file in the project root:
```
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Test Basic Functionality
```bash
python quick_test.py
```

### 4. Run Full Analysis (with API)
```bash
python test_agent.py
```

## What We've Built

### Core Features
- **PDF Transcript Extraction**: Automatically extracts text from PDF interview transcripts
- **Confidence Assessment**: Analyzes witness confidence levels based on language patterns
- **Entity Extraction**: Identifies people, places, and time references
- **Importance Scoring**: Ranks interview sections by importance (1-10 scale)
- **Comprehensive Analysis**: Provides summaries and detailed breakdowns

### Key Components

1. **InterviewAnalystAgent** (`Interview_agent.py`)
   - Main analysis engine
   - Handles PDF extraction, confidence rating, entity extraction
   - Works with or without API (fallback heuristics when API unavailable)

2. **Test Suite** (`test_agent.py`)
   - Complete analysis workflow
   - Saves results to JSON files
   - Comprehensive error handling

3. **Quick Test** (`quick_test.py`)
   - Basic functionality verification
   - Dependency checking
   - Environment validation

4. **Examples** (`example_usage.py`)
   - Demonstrates different use cases
   - Shows confidence analysis, entity extraction, importance scoring

## Analysis Results

The system provides structured output including:

- **Summary**: AI-generated comprehensive summary of the interview
- **Statistics**: Total sections, important sections, confidence levels
- **Entity Extraction**: People, places, and times mentioned
- **Confidence Analysis**: High/medium/low confidence sections
- **Importance Scoring**: Sections rated 7+ on importance scale

## Confidence Assessment

The system analyzes language patterns:

**Low Confidence Indicators:**
- "think", "maybe", "unsure", "not sure", "can't remember"

**Medium Confidence Indicators:**
- "probably", "presumably", "around", "about"

**High Confidence Indicators:**
- "definitely", "absolutely", "I saw", "I know", "I remember"

## Testing Without API

The system works without an API key for basic functionality:
- PDF text extraction
- Confidence rating (based on language patterns)
- Section parsing
- Basic entity extraction (fallback heuristics)

## Testing With API

With an API key, you get:
- AI-powered entity extraction
- Intelligent importance scoring
- Comprehensive summaries
- Advanced analysis

## Sample Output

The system generates files like:
- `analysis_results.json`: Complete analysis results
- `custom_analysis_results.json`: Custom workflow results

## Customization

You can modify:
- Confidence indicators in `assign_confidence_rating()`
- Importance criteria in `identify_important_sections()`
- Entity extraction prompts in `extract_entities()`
- Summary generation in `analyze_transcript()`

## Troubleshooting

### Common Issues:
1. **Missing API Key**: System works with fallback heuristics
2. **PDF Extraction Errors**: Check file format and permissions
3. **Import Errors**: Run `pip install -r requirements.txt`

### Error Handling:
- Graceful degradation when API unavailable
- Comprehensive error messages
- Fallback functionality for core features

## Next Steps

1. **Get API Key**: Sign up at OpenAI for full functionality
2. **Test with Your Transcripts**: Replace sample PDF with your files
3. **Customize Analysis**: Modify prompts for your specific needs
4. **Scale Up**: Process multiple transcripts in batch

## File Structure
```
MissingPersonsInterviewAgent/
├── Interview_agent.py     # Main analysis agent
├── test_agent.py         # Full test suite
├── quick_test.py         # Basic functionality test
├── example_usage.py      # Usage examples
├── requirements.txt      # Dependencies
├── README.md            # Documentation
├── SETUP.md             # This file
└── Mock Search 3-8-25 transcription 2.pdf  # Sample transcript
```

The system is now ready for production use with interview transcript analysis! 