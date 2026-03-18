#!/usr/bin/env python3
"""
Weather Agent request/response test helper.

Examples:
  poetry run python -m agents.weather.test_weather_agent --location "San Luis Obispo, CA"
  poetry run python -m agents.weather.test_weather_agent --location "Dublin, CA"
  poetry run python -m agents.weather.test_weather_agent --lat 35.2828 --lon -120.6596
"""

import argparse
import json
import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

from shared import RedisBus, wrap_envelope, parse_message_from_stream

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REQUEST_STREAM = "weather.request.raw"
FORECAST_STREAM = "weather.forecast.raw"
DEAD_LETTER_STREAM = "system.dead_letter"
OPENAI_MODEL = os.getenv("WEATHER_ANALYSIS_MODEL", "gpt-4.1-mini")
WEATHER_ANALYSIS_SYSTEM_PROMPT = """You are a weather analysis specialist focused on analyzing weather impact on search and rescue operations.

Your responsibilities:
1. Call get_weather_data() function to read weather data from Redis
2. Analyze weather data (temperature, wind speed, visibility, precipitation, etc.)
3. Assess weather conditions' impact on search operations
4. Provide specific action recommendations (e.g., postpone search during rain, or take precautions in cold temperatures)

When asked about weather, first call get_weather_data() to get the latest data, then analyze.
Provide clear, actionable recommendations."""


def build_request_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.location:
        return {"location_name": args.location}
    return {"latitude": args.lat, "longitude": args.lon}


def extract_message_id(message: Any) -> Optional[str]:
    if hasattr(message, "envelope") and hasattr(message.envelope, "message_id"):
        return message.envelope.message_id
    if isinstance(message, dict):
        envelope = message.get("envelope")
        if isinstance(envelope, dict):
            return envelope.get("message_id")
        return message.get("message_id")
    return None


def publish_weather_request(bus: RedisBus, payload: Dict[str, Any]) -> str:
    message = wrap_envelope(
        payload=payload,
        source_name="weather-test-client",
        source_version="1.0",
        target_stream=REQUEST_STREAM,
    )
    request_message_id = extract_message_id(message)
    if not request_message_id:
        raise RuntimeError("Unable to determine request message_id before publishing.")

    bus.publish(message)
    print(f"Published weather request -> {REQUEST_STREAM}")
    print(json.dumps(payload, indent=2))
    return request_message_id


def decode_stream_entry(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        (k.decode("utf-8") if isinstance(k, (bytes, bytearray)) else k):
        (v.decode("utf-8") if isinstance(v, (bytes, bytearray)) else v)
        for k, v in raw_data.items()
    }


def parse_payload(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    decoded = decode_stream_entry(raw_data)
    parsed = parse_message_from_stream(decoded)
    if not parsed:
        return {}

    payload = getattr(parsed, "payload", {})
    return payload if isinstance(payload, dict) else {}


def read_matching_forecast(bus: RedisBus, request_message_id: str, count: int = 10) -> Dict[str, Any]:
    messages = bus.client.xrevrange(FORECAST_STREAM, count=count)
    for _msg_id, raw_data in messages:
        payload = parse_payload(raw_data)
        request_info = payload.get("request", {})
        if request_info.get("request_message_id") == request_message_id:
            return payload
    return {}


def read_matching_dead_letter(bus: RedisBus, request_message_id: str, count: int = 10) -> Dict[str, Any]:
    messages = bus.client.xrevrange(DEAD_LETTER_STREAM, count=count)
    for _msg_id, raw_data in messages:
        payload = parse_payload(raw_data)
        if request_message_id in str(payload.get("context", "")):
            return payload
    return {}


def wait_for_weather_response(
    bus: RedisBus,
    request_message_id: str,
    wait_seconds: int,
) -> Dict[str, Any]:
    deadline = time.time() + max(wait_seconds, 1)
    while time.time() < deadline:
        forecast_payload = read_matching_forecast(bus, request_message_id)
        if forecast_payload:
            return forecast_payload

        error_payload = read_matching_dead_letter(bus, request_message_id)
        if error_payload:
            raise RuntimeError(json.dumps(error_payload, indent=2))

        time.sleep(1)

    return {}


def read_latest_forecast(bus: RedisBus) -> Dict[str, Any]:
    messages = bus.client.xrevrange(FORECAST_STREAM, count=1)
    if not messages:
        return {}

    _msg_id, raw_data = messages[0]
    return parse_payload(raw_data)


def analyze_weather_with_llm(forecast_payload: Dict[str, Any], model: str) -> str:
    client = OpenAI()
    user_prompt = (
        "Analyze the following weather forecast payload for search and rescue operations. "
        "Summarize the operational impact and provide clear actionable recommendations.\n\n"
        f"{json.dumps(forecast_payload, indent=2)}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": WEATHER_ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


def maybe_analyze_weather(forecast_payload: Dict[str, Any], args: argparse.Namespace) -> None:
    if args.skip_llm:
        return
    if not os.getenv("OPENAI_API_KEY"):
        print("\nSkipping LLM analysis because OPENAI_API_KEY is not set.")
        return

    try:
        analysis = analyze_weather_with_llm(forecast_payload, args.model)
    except Exception as e:
        print(f"\nLLM analysis failed: {e}")
        return

    print(f"\nLLM analysis ({args.model}):")
    print(analysis)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a weather request, print the response, and optionally run a single LLM analysis."
    )
    parser.add_argument("--location", help="Location name to geocode, e.g. 'San Luis Obispo, CA'")
    parser.add_argument("--lat", type=float, help="Latitude")
    parser.add_argument("--lon", type=float, help="Longitude")
    parser.add_argument("--wait-seconds", type=int, default=10, help="Max time to wait for the matching response.")
    parser.add_argument("--model", default=OPENAI_MODEL, help="OpenAI model used for weather analysis.")
    parser.add_argument("--skip-llm", action="store_true", help="Skip the final LLM weather analysis step.")
    args = parser.parse_args()

    using_location = bool(args.location)
    using_coords = args.lat is not None or args.lon is not None

    if using_location and using_coords:
        parser.error("Use either --location or --lat/--lon, not both.")
    if not using_location and not using_coords:
        parser.error("Provide --location or both --lat and --lon.")
    if using_coords and (args.lat is None or args.lon is None):
        parser.error("Both --lat and --lon are required when using coordinates.")

    return args


def main() -> None:
    args = parse_args()
    bus = RedisBus(REDIS_URL)
    request_payload = build_request_payload(args)

    request_message_id = publish_weather_request(bus, request_payload)
    print(f"Waiting up to {args.wait_seconds} seconds for weather agent processing...")

    try:
        forecast_payload = wait_for_weather_response(bus, request_message_id, args.wait_seconds)
    except RuntimeError as e:
        print(f"Weather request failed:\n{e}")
        return

    if not forecast_payload:
        forecast_payload = read_latest_forecast(bus)
    if not forecast_payload:
        print(f"No forecast found in {FORECAST_STREAM}.")
        return

    print(f"\nLatest forecast from {FORECAST_STREAM}:")
    print(json.dumps(forecast_payload, indent=2))
    maybe_analyze_weather(forecast_payload, args)


if __name__ == "__main__":
    main()
