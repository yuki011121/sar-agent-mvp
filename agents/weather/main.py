# agents/weather/main.py

"""
Weather Agent (v2.0)

Consumes weather requests from Redis and publishes normalized forecast outputs.
Accepted request payloads:
1) {"location_name": "San Luis Obispo, CA"}
2) {"latitude": 35.2828, "longitude": -120.6596}
"""

import os
import logging
from typing import Any, Dict, Optional, Tuple
import requests

from shared import wrap_envelope, RedisBus

AGENT_NAME = os.getenv("AGENT_NAME", "weather-agent")
AGENT_VERSION = os.getenv("AGENT_VERSION", "2.0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REQUEST_STREAM = os.getenv("WEATHER_REQUEST_STREAM", "weather.request.raw")
FORECAST_STREAM = "weather.forecast.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

DEFAULT_LATITUDE = os.getenv("LATITUDE", "35.2828")
DEFAULT_LONGITUDE = os.getenv("LONGITUDE", "-120.6596")
ENABLE_STARTUP_DEFAULT_FETCH = os.getenv("ENABLE_STARTUP_DEFAULT_FETCH", "false").lower() == "true"

API_USER_AGENT = os.getenv("WEATHER_API_USER_AGENT", "SAR-Multi-Agent-System")
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 30))
BLOCK_MS = int(os.getenv("WEATHER_REQUEST_BLOCK_MS", 30000))
NOMINATIM_SEARCH_URL = os.getenv("NOMINATIM_SEARCH_URL", "https://nominatim.openstreetmap.org/search")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)


def _to_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}: {value!r}. Must be numeric.")


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if latitude < -90 or latitude > 90:
        raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and 90.")
    if longitude < -180 or longitude > 180:
        raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and 180.")


def _extract_coords_from_payload(payload: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat_keys = ("latitude", "lat")
    lon_keys = ("longitude", "lon", "lng")

    lat_value = next((payload[k] for k in lat_keys if k in payload), None)
    lon_value = next((payload[k] for k in lon_keys if k in payload), None)

    location = payload.get("location")
    if isinstance(location, dict):
        if lat_value is None:
            lat_value = next((location[k] for k in lat_keys if k in location), None)
        if lon_value is None:
            lon_value = next((location[k] for k in lon_keys if k in location), None)

    if lat_value is None and lon_value is None:
        return None
    if lat_value is None or lon_value is None:
        raise ValueError("Both latitude and longitude are required when using coordinates.")

    latitude = _to_float(lat_value, "latitude")
    longitude = _to_float(lon_value, "longitude")
    _validate_coordinates(latitude, longitude)
    return latitude, longitude


def _extract_location_name(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("location_name", "place_name", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    location = payload.get("location")
    if isinstance(location, str) and location.strip():
        return location.strip()
    if isinstance(location, dict):
        for key in ("name", "location_name", "place_name"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def geocode_location_name(location_name: str) -> Tuple[float, float, Optional[str]]:
    headers = {"User-Agent": API_USER_AGENT}
    params = {
        "q": location_name,
        "format": "jsonv2",
        "limit": 1,
    }

    logger.info("Geocoding location name: %s", location_name)
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params=params,
        headers=headers,
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    candidates = response.json()

    if not isinstance(candidates, list) or not candidates:
        raise ValueError(f"No coordinates found for location: {location_name}")

    best_match = candidates[0]
    latitude = _to_float(best_match.get("lat"), "latitude")
    longitude = _to_float(best_match.get("lon"), "longitude")
    _validate_coordinates(latitude, longitude)
    display_name = best_match.get("display_name")
    return latitude, longitude, display_name


def resolve_request_coordinates(payload: Dict[str, Any]) -> Tuple[float, float, Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Request payload must be a JSON object.")

    coords = _extract_coords_from_payload(payload)
    if coords is not None:
        latitude, longitude = coords
        return latitude, longitude, {"resolution_method": "provided_coordinates"}

    location_name = _extract_location_name(payload)
    if location_name:
        latitude, longitude, display_name = geocode_location_name(location_name)
        return latitude, longitude, {
            "resolution_method": "geocoded_location_name",
            "requested_location_name": location_name,
            "resolved_location_name": display_name,
        }

    raise ValueError(
        "Weather request must include either location_name or both latitude and longitude."
    )


def fetch_forecast_for_coordinates(latitude: float, longitude: float) -> Dict[str, Any]:
    headers = {"User-Agent": API_USER_AGENT}
    points_url = f"https://api.weather.gov/points/{latitude},{longitude}"

    logger.info("Fetching weather metadata from %s", points_url)
    points_response = requests.get(points_url, headers=headers, timeout=HTTP_TIMEOUT)
    points_response.raise_for_status()

    points_properties = points_response.json()["properties"]
    forecast_url = points_properties["forecast"]

    logger.info("Fetching weather forecast from %s", forecast_url)
    forecast_response = requests.get(forecast_url, headers=headers, timeout=HTTP_TIMEOUT)
    forecast_response.raise_for_status()

    forecast_periods = forecast_response.json()["properties"]["periods"]
    return {
        "source_api": "NOAA NWS API",
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "forecast_metadata": {
            "forecast_url": forecast_url,
            "forecast_office": points_properties.get("forecastOffice"),
            "grid_id": points_properties.get("gridId"),
            "grid_x": points_properties.get("gridX"),
            "grid_y": points_properties.get("gridY"),
            "city": points_properties.get("relativeLocation", {}).get("properties", {}).get("city"),
            "state": points_properties.get("relativeLocation", {}).get("properties", {}).get("state"),
        },
        "forecasts": forecast_periods,
    }


def publish_dead_letter(bus: RedisBus, context: str, error: Exception, request_payload: Any) -> None:
    logger.error("%s: %s", context, error, exc_info=True)
    error_payload = {
        "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
        "error_message": str(error),
        "error_type": type(error).__name__,
        "context": context,
        "request_payload": request_payload,
    }
    error_message = wrap_envelope(
        payload=error_payload,
        source_name=AGENT_NAME,
        source_version=AGENT_VERSION,
        target_stream=DEAD_LETTER_STREAM,
    )
    bus.publish(error_message)


def process_weather_request(bus: RedisBus, request_payload: Dict[str, Any], request_message_id: str) -> None:
    try:
        latitude, longitude, resolution_metadata = resolve_request_coordinates(request_payload)
        payload = fetch_forecast_for_coordinates(latitude, longitude)
        payload["request"] = {
            "request_message_id": request_message_id,
            **resolution_metadata,
        }

        forecast_message = wrap_envelope(
            payload=payload,
            source_name=AGENT_NAME,
            source_version=AGENT_VERSION,
            target_stream=FORECAST_STREAM,
        )
        bus.publish(forecast_message)
        logger.info(
            "Published weather forecast for request %s -> %s",
            request_message_id,
            FORECAST_STREAM,
        )
    except Exception as e:
        publish_dead_letter(
            bus=bus,
            context=(
                "Failed while processing weather request "
                f"message_id={request_message_id}"
            ),
            error=e,
            request_payload=request_payload,
        )


def run_startup_default_fetch_if_enabled(bus: RedisBus) -> None:
    if not ENABLE_STARTUP_DEFAULT_FETCH:
        return
    try:
        latitude = _to_float(DEFAULT_LATITUDE, "latitude")
        longitude = _to_float(DEFAULT_LONGITUDE, "longitude")
        _validate_coordinates(latitude, longitude)
        process_weather_request(
            bus=bus,
            request_payload={"latitude": latitude, "longitude": longitude},
            request_message_id="startup-default-fetch",
        )
    except Exception as e:
        publish_dead_letter(
            bus=bus,
            context="Failed during startup default weather fetch",
            error=e,
            request_payload={"latitude": DEFAULT_LATITUDE, "longitude": DEFAULT_LONGITUDE},
        )


def main():
    logger.info(f"Initializing {AGENT_NAME}...")

    try:
        bus = RedisBus(REDIS_URL)
    except Exception as e:
        logger.critical(f"Failed to connect to Redis, cannot start agent. Error: {e}")
        return 

    logger.info("%s starting up. Listening on stream: %s", AGENT_NAME, REQUEST_STREAM)
    run_startup_default_fetch_if_enabled(bus)

    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-group",
            consumer_name=f"{AGENT_NAME}-consumer",
            streams=[REQUEST_STREAM],
            block_ms=BLOCK_MS,
        ):
            logger.info(
                "Processing weather request message_id=%s",
                message.envelope.message_id,
            )
            process_weather_request(
                bus=bus,
                request_payload=message.payload,
                request_message_id=message.envelope.message_id,
            )
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down weather agent.")
    except Exception as e:
        publish_dead_letter(
            bus=bus,
            context="Unexpected error in weather agent subscribe loop",
            error=e,
            request_payload={},
        )


if __name__ == "__main__":
    main()
