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
    assert result["schema_version"] == "decision_map_v2"
    assert result["views"]["command"]["node_ids"]
    assert result["views"]["analyze"]["node_ids"]
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


def test_history_cases_are_split_and_ranked():
    entries = [
        _entry("history", "history.out.raw", {
            "matches_found": 3,
            "matched_cases": [
                {"Incident.Outcome": "found alive", "Terrain": "forest", "Subject.Category": "elderly", "Age": "72", "Subject.Status": "well"},
                {"Incident.Outcome": "medical evacuation", "Terrain": "trail", "Subject.Category": "diabetic", "Age": "65", "Subject.Status": "injured"},
                {"Incident.Outcome": "found near water", "Terrain": "creek", "Subject.Activity": "walkaway", "Age": "67"},
            ],
        }),
    ]

    result = build_session_fact_graph(entries, "s1")
    history_nodes = [
        node for node in result["nodes"]
        if node["type"] == "event" and node["canonical_key"].startswith("event:history")
    ]

    assert any(node["label"] == "Historical patterns" for node in result["nodes"])
    assert len(history_nodes) == 3
    assert all(node["priority_score"] > 0 for node in result["nodes"])
    assert all(node["priority_tier"] in {"critical", "high", "medium", "low"} for node in result["nodes"])


def test_history_count_without_details_keeps_aggregate_warning():
    result = build_session_fact_graph(
        [_entry("history", "history.out.raw", {"matches_found": 3, "actions": "Search trail corridors."})],
        "s1",
    )

    assert not [
        node for node in result["nodes"]
        if node["canonical_key"].startswith("event:history") and node["label"] != "3 similar cases"
    ]
    assert result["debug"]["payload_shapes"]["history"]["warning"] == "case details unavailable from history payload"
    aggregate = next(node for node in result["nodes"] if node["label"] == "3 similar cases")
    assert aggregate["details"]["Case details"] == "Case details unavailable from history payload"


def test_anchor_prevents_weather_health_history_islands():
    entries = [
        _entry("weather", "weather.forecast.raw", {"forecasts": [{"shortForecast": "Sunny", "temperature": 85}]}),
        _entry("health", "health.assessment.raw", {"assessment": {"risk_level": "HIGH", "primary_health_risks": [{"condition": "Dehydration", "severity": "HIGH"}]}}),
        _entry("history", "history.out.raw", {"matches_found": 1, "matched_cases": [{"Terrain": "desert", "Subject.Category": "elderly"}]}),
    ]

    result = build_session_fact_graph(entries, "s1")
    incident = next(node for node in result["nodes"] if node["label"] == "Current incident")
    linked_ids = {edge["source"] for edge in result["edges"]} | {edge["target"] for edge in result["edges"]}

    assert incident["id"] in linked_ids
    assert result["debug"]["unlinked_node_count"] == 0


def test_cross_agent_weather_and_history_support_health_risks():
    entries = [
        _entry("weather", "weather.forecast.raw", {"forecasts": [{"shortForecast": "Cold wind", "temperature": 34, "windSpeed": "25 mph"}]}),
        _entry("health", "health.assessment.raw", {
            "assessment": {
                "risk_level": "HIGH",
                "primary_health_risks": [
                    {"condition": "Hypothermia", "severity": "HIGH", "reasoning": "Cold wind and exposure"},
                    {"condition": "Diabetic emergency", "severity": "CRITICAL", "reasoning": "65-year-old diabetic"},
                ],
            },
        }),
        _entry("history", "history.out.raw", {
            "matches_found": 1,
            "matched_cases": [{"Incident.Outcome": "medical evacuation", "Terrain": "trail", "Subject.Category": "diabetic", "Age": "65"}],
        }),
    ]

    result = build_session_fact_graph(entries, "s1")

    assert any(edge["type"] == "exacerbates" for edge in result["edges"])
    assert any(edge["type"] == "supports_risk" for edge in result["edges"])


def test_decision_map_v2_command_view_is_operational_subset():
    entries = [
        _entry("path", "path.analysis.raw", {
            "lkp": {"lat": 35.2828, "lon": -120.6596},
            "person_class": "active adult",
            "person_profile": "Active Adult",
            "probability_points": [
                {"lat": 35.29, "lon": -120.66, "endpoint_probability": 0.31, "rank": 1},
                {"lat": 35.30, "lon": -120.67, "endpoint_probability": 0.22, "rank": 2},
                {"lat": 35.31, "lon": -120.68, "endpoint_probability": 0.16, "rank": 3},
                {"lat": 35.32, "lon": -120.69, "endpoint_probability": 0.12, "rank": 4},
            ],
        }),
        _entry("weather", "weather.forecast.raw", {
            "forecasts": [{"shortForecast": "Sunny", "temperature": 84}],
        }),
        _entry("health", "health.assessment.raw", {
            "assessment": {
                "risk_level": "HIGH",
                "primary_health_risks": [
                    {"condition": "Dehydration", "severity": "CRITICAL"},
                    {"condition": "Diabetic emergency", "severity": "CRITICAL"},
                    {"condition": "Heat exhaustion", "severity": "HIGH"},
                    {"condition": "Fatigue", "severity": "MEDIUM"},
                ],
            },
        }),
        _entry("history", "history.out.raw", {
            "matches_found": 1,
            "matched_cases": [{"Incident.Outcome": "found alive", "Terrain": "trail"}],
        }),
    ]

    result = build_session_fact_graph(entries, "s1")
    command = result["views"]["command"]
    analyze = result["views"]["analyze"]
    command_nodes = [n for n in result["nodes"] if n["id"] in set(command["node_ids"])]
    command_edges = [e for e in result["edges"] if e["id"] in set(command["edge_ids"])]

    assert result["schema_version"] == "decision_map_v2"
    assert set(analyze["node_ids"]) == {n["id"] for n in result["nodes"]}
    assert set(analyze["edge_ids"]) == {e["id"] for e in result["edges"]}
    assert {n["role"] for n in command_nodes} >= {"incident", "subject", "lkp", "search_area", "risk"}
    assert len([n for n in command_nodes if n["role"] == "search_area"]) <= 3
    assert len([n for n in command_nodes if n["role"] == "history"]) == 0
    assert all(e["importance"] in {"primary", "supporting"} for e in command_edges)
    assert all(e["show_in_command"] for e in command_edges)
    assert any(n["display_label"] == "Last known position" and n["geo"] for n in command_nodes)
