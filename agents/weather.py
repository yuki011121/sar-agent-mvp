# agents/weather.py
import requests
import os
from utils.redis_bus import publish

# eg：San Luis Obispo, CA
LATITUDE = "35.2828"
LONGITUDE = "-120.6596"
STREAM_NAME = "agent.weather.out"

def call_noaa_api():
    """
    Calls the NOAA API in a two-step process to get the latest weather forecast.
    """
    headers = {"User-Agent": "SAR-Agent-PoC (student.project@example.com)"}
    points_url = f"https://api.weather.gov/points/{LATITUDE},{LONGITUDE}"
    print(f"Weather Agent: Step 1 - Fetching metadata from {points_url}")
    
    points_response = requests.get(points_url, headers=headers, timeout=10)
    points_response.raise_for_status()  
    
    forecast_url = points_response.json()["properties"]["forecast"]
    print(f"Weather Agent: Step 1 - Got forecast URL: {forecast_url}")

    print("Weather Agent: Step 2 - Fetching actual forecast data...")
    forecast_response = requests.get(forecast_url, headers=headers, timeout=10)
    forecast_response.raise_for_status()
    
    data = forecast_response.json()
    
    period = data["properties"]["periods"][0]
    
    print(f"Weather Agent: Successfully fetched forecast for {period['name']}")
    
    payload = {
        "location": "San Luis Obispo, CA",
        "period": period["name"],
        "startTime": period["startTime"],
        "endTime": period["endTime"],
        "temperature": f'{period["temperature"]} {period["temperatureUnit"]}',
        "wind": f'{period["windSpeed"]} {period["windDirection"]}',
        "shortForecast": period["shortForecast"],
    }
    return payload

if __name__ == "__main__":
    print("Weather Agent: Starting...")
    try:
        forecast_payload = call_noaa_api()
        print("Weather Agent: Publishing forecast to Redis...")
        publish(
            stream_name=STREAM_NAME,
            payload=forecast_payload,
            msg_type="weather.forecast",
            sender="weather-agent-v1"
        )
        print("Weather Agent: Done.")
    except requests.exceptions.HTTPError as e:
        print(f"ERROR: Failed to get weather data. {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")