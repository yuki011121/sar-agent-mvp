# Interview Transcript Analysis Agent

An AI-powered system for analyzing PDF interview transcripts to identify important information, extract entities, and assess confidence levels in witness statements.

## Features

- **PDF Transcript Extraction**: Automatically extracts text from PDF interview transcripts
- **Entity Extraction**: Identifies people, places, and time references mentioned in interviews
- **Confidence Assessment**: Analyzes witness confidence levels based on language indicators
- **Importance Scoring**: Identifies and ranks the most important sections of interviews
- **Comprehensive Analysis**: Provides summaries, statistics, and detailed breakdowns

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   - Create a `.env` file in the project root
   - Add your OpenAI API key:
     ```
     OPENAI_API_KEY=your_openai_api_key_here
     ```

## Usage

### Basic Usage

Run the test script to analyze a transcript:

```bash
python test_agent.py
```

This will:
- Test the confidence rating functionality
- Analyze the PDF transcript file
- Display results in the console
- Save detailed results to `analysis_results.json`

### Programmatic Usage

```python
from Interview_agent import InterviewAnalystAgent

# Initialize the agent
agent = InterviewAnalystAgent(
    name="Interview Analyst",
    role="Transcript Analyst",
    system_message="Specialized in analyzing interview transcripts",
    input_text=""
)

# Analyze a transcript file
results = agent.analyze_transcript('your_transcript.pdf')

# Access different analysis components
summary = results['summary']
important_sections = results['important_sections']
entity_extraction = results['entity_extraction']
confidence_analysis = results['confidence_analysis']
```

## Analysis Components

### 1. Confidence Assessment
The system analyzes language patterns to assess witness confidence:
- **Low Confidence**: "think", "maybe", "unsure", "not sure"
- **Medium Confidence**: "probably", "presumably", "around"
- **High Confidence**: "definitely", "absolutely", "I saw", "I know"

### 2. Entity Extraction
Automatically identifies:
- **People**: Names and identifying information
- **Places**: Addresses and locations mentioned
- **Times**: Dates, times, and time periods

### 3. Importance Scoring
Rates interview sections on a scale of 1-10 based on:
- Key details about missing persons
- Critical timeline information
- Important locations
- Key witnesses
- Crucial evidence

### 4. Comprehensive Summary
Generates a detailed summary highlighting:
- Key findings and important information
- Critical timeline details
- Important locations or addresses
- Key witnesses or people involved
- Inconsistencies or areas needing clarification

## Output Format

The analysis returns a structured dictionary with:

```python
{
    "summary": "Comprehensive summary of the interview",
    "total_sections": 15,
    "confidence_analysis": [
        {
            "section": "Interview text section",
            "confidence_score": 5,
            "confidence_level": "medium"
        }
    ],
    "entity_extraction": [
        {
            "section": "Interview text section",
            "entities": {
                "people": ["John Smith", "Jane Doe"],
                "places": ["123 Main St", "Downtown Mall"],
                "times": ["March 15th", "3:30 PM"]
            }
        }
    ],
    "important_sections": [
        {
            "section": "Important interview section",
            "importance_score": 8,
            "reason": "Contains critical timeline information"
        }
    ],
    "high_confidence_sections": [...],
    "low_confidence_sections": [...]
}
```

## Testing

The system includes built-in testing:

1. **Confidence Rating Test**: Tests the confidence assessment functionality
2. **Full Analysis Test**: Performs complete analysis on a sample transcript
3. **Error Handling**: Comprehensive error handling for API calls and file operations

## File Structure

```
MissingPersonsInterviewAgent/
├── base_agent.py          # Base agent class with common functionality
├── Interview_agent.py     # Main interview analysis agent
├── test_agent.py         # Testing and demonstration script
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── .env                 # Environment variables (create this)
└── Mock Search 3-8-25 transcription 2.pdf  # Sample transcript
```

## Error Handling

The system includes robust error handling for:
- Missing API keys
- Invalid PDF files
- API rate limits
- Network connectivity issues
- JSON parsing errors

## Customization

You can customize the analysis by modifying:

1. **Confidence Indicators**: Update the confidence_indicators dictionary in `assign_confidence_rating()`
2. **Importance Criteria**: Modify the prompt in `identify_important_sections()`
3. **Entity Extraction**: Adjust the extraction prompt in `extract_entities()`
4. **Summary Generation**: Customize the summary prompt in `analyze_transcript()`

## Requirements

- Python 3.7+
- OpenAI API key
- PDF files to analyze

## License

This project is for educational and research purposes. 