# Health Agent

The Health Agent performs medical risk assessments for missing persons in search and rescue operations.

## Overview

The Health Agent:
- Performs initial medical assessments when a new mission begins
- Continuously updates health status based on real-time field observations
- Triggers alerts and requests medical supplies when situations become critical
- Uses LLM (GPT-4) to analyze complex health scenarios

## Architecture

### Inputs (Redis Streams)
- `mission.new`: Missing person's profile (age, gender, known conditions, clothing)
- `weather.forecast.raw`: Environmental data (temperature, wind, precipitation)
- `field.observation.raw`: Field team updates (symptoms, consciousness, injuries)

### Outputs (Redis Streams)
- `health.assessment.raw`: Medical assessment reports with risk levels
- `logistics.requests.raw`: Medical supply requests when needed

## Workflow

1. **Data Aggregation**: Builds a HealthProfile object from multiple sources
2. **LLM Analysis**: Generates prompt with full health context
3. **Risk Assessment**: LLM returns structured JSON with:
   - Top health risks
   - Overall health status (HIGH/MEDIUM/LOW)
   - Recommended actions
   - Required medical supplies
4. **Action Triggers**: Publishes logistics requests if critical

## Configuration

Environment variables:
- `REDIS_URL`: Redis connection URL (default: redis://localhost:6379)
- `UPDATE_INTERVAL_SECONDS`: Assessment frequency (default: 60)
- `OPENAI_API_KEY`: OpenAI API key for GPT-4 (optional, uses mock data if not set)

## Running the Agent

```bash
# With Poetry
poetry run python -m agents.health.main

# Or directly
python agents/health/main.py
```

## Example Assessment Output

```json
{
  "risk_level": "HIGH",
  "primary_health_risks": [
    {
      "condition": "Hypothermia",
      "severity": "critical",
      "reasoning": "Extended exposure to 45°F with high winds"
    },
    {
      "condition": "Diabetic emergency",
      "severity": "serious",
      "reasoning": "Type 2 diabetes, 36 hours without medication"
    }
  ],
  "recommended_actions": [
    "Immediate shelter and warming required",
    "Check blood glucose levels upon contact",
    "Prepare insulin and glucose supplies"
  ],
  "required_supplies": [
    {
      "item": "Emergency blankets",
      "quantity": "3",
      "priority": "urgent"
    },
    {
      "item": "Glucose tablets",
      "quantity": "20",
      "priority": "urgent"
    }
  ],
  "logistics_request_needed": true
}
```

## Integration with Other Agents

- **Weather Agent**: Provides environmental conditions for exposure risk assessment
- **Logistics Agent**: Receives medical supply requests
- **Commander Agent**: Receives health status updates for mission planning

## Development Notes

- Uses hardcoded data when Redis streams are empty (for testing)
- Falls back to mock LLM responses when OPENAI_API_KEY is not set
- Designed for containerization with Docker