import pytest
from sar_project.agents.weather_agent import WeatherAgent

class TestWeatherAgent:
    @pytest.fixture
    def agent(self):
        return WeatherAgent()

    def test_initialization(self, agent):
        assert agent.name == "weather_specialist"
        assert agent.role == "Weather Specialist"
        assert agent.mission_status == "standby"

    def test_process_request(self, agent):
        message = {
            "get_conditions": True,
            "location": "test_location"
        }
        response = agent.process_request(message)
        assert "temperature" in response
        assert "wind_speed" in response

    def test_risk_assessment(self, agent):
        response = agent.assess_weather_risk("test_location")
        assert "risk_level" in response
        assert "risks" in response
        assert "recommendations" in response

    def test_status_update(self, agent):
        response = agent.update_status("active")
        assert response["new_status"] == "active"
        assert agent.get_status() == "active"
