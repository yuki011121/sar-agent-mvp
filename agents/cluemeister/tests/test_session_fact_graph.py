#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fact_graph import SessionFactGraph, build_session_fact_graph, _source


def _entry(agent, stream, data):
    data = {"session_id": "s1", "turn_id": "t1", **data}
    return {"agent": agent, "stream": stream, "data": data}


def test_path_health_weather_create_multi_node_graph():
    entries = [
        _entry("path", "path.analysis.raw", {
            "lkp": {"lat": 40.1, "lon": -73.9},
            "person_class": "active adult",
            "person_profile": "Active Adult",
            "search_radius_km": {"p50": 1.2, "p95": 3.4},
            "probability_points": [
                {"lat": 40.11, "lon": -73.91, "endpoint_probability": 0.25, "rank": 1},
                {"lat": 40.12, "lon": -73.92, "endpoint_probability": 0.18, "rank": 2},
            ],
        }),
        _entry("weather", "weather.forecast.raw", {
            "forecasts": [{"shortForecast": "Cold wind", "temperature": 42, "temperatureUnit": "F"}],
        }),
        _entry("health", "health.assessment.raw", {
            "assessment": {
                "risk_level": "HIGH",
                "primary_health_risks": [
                    {"condition": "Hypothermia", "severity": "HIGH", "reasoning": "Cold wind"},
                    {"condition": "Dehydration", "severity": "MEDIUM"},
                ],
            },
        }),
    ]

    result = build_session_fact_graph(entries, "s1")

    assert len(result["nodes"]) >= 7
    assert len(result["edges"]) >= 6
    assert any(n["type"] == "search_area" for n in result["nodes"])
    assert any(e["type"] == "exacerbates" for e in result["edges"])


def test_fuzzy_merge_and_edge_dedupe():
    graph = SessionFactGraph()
    entry = _entry("interview", "interview.analysis.raw", {})
    source = _source(entry, "test", "Central Park Lake")

    first = graph.add_node("location", "Central Park Lake", 0.7, source)
    second = graph.add_node("location", "central park lake", 0.8, source)
    person = graph.add_node("person", "Missing Person", 0.9, source, canonical_seed="missing person")
    graph.add_edge(person, first, "last_seen", 0.6, source)
    graph.add_edge(person, second, "last_seen", 0.8, source)
    result = graph.export()

    assert first == second
    assert len([n for n in result["nodes"] if n["type"] == "location"]) == 1
    assert len(result["edges"]) == 1
    assert result["edges"][0]["confidence"] == 0.8


def test_session_builder_does_not_use_other_session_data():
    s1 = [_entry("history", "history.out.raw", {"matches_found": 1, "matched_cases": [{"Terrain": "forest"}]})]
    s2 = [_entry("history", "history.out.raw", {"session_id": "s2", "turn_id": "t2", "matches_found": 3})]

    result = build_session_fact_graph(s1, "s1")

    assert result["debug"]["payload_entries"] == 1
    assert all(
        all(src["session_id"] == "s1" for src in node["sources"])
        for node in result["nodes"]
    )
    assert s2
