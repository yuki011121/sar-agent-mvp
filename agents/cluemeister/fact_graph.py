#!/usr/bin/env python3
"""
Session-scoped fact graph builder for ClueMeister.

Agent payloads are normalized into facts before visualization. This keeps the
clue map deterministic and useful even when the LLM summary layer is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import networkx as nx
from pydantic import BaseModel, Field

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - fallback for local envs without deps
    fuzz = None
    from difflib import SequenceMatcher


NODE_TYPE_THRESHOLDS = {
    "person": 84,
    "location": 84,
    "search_area": 84,
}
DEFAULT_FUZZY_THRESHOLD = 88


class EvidenceSource(BaseModel):
    agent: str
    stream: str
    session_id: str = ""
    turn_id: str = ""
    field_path: str = ""
    excerpt: str = ""
    timestamp: str = ""


class ClueFactNode(BaseModel):
    id: str
    type: str
    label: str
    canonical_key: str
    confidence: float = 0.5
    sources: List[EvidenceSource] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class ClueFactEdge(BaseModel):
    source: str
    target: str
    type: str
    confidence: float = 0.5
    sources: List[EvidenceSource] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class ClueMapResult(BaseModel):
    nodes: List[ClueFactNode] = Field(default_factory=list)
    edges: List[ClueFactEdge] = Field(default_factory=list)
    debug: Dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9.\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean_text(value))


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _score(a: str, b: str) -> float:
    if fuzz is not None:
        return float(fuzz.token_set_ratio(a, b))
    return SequenceMatcher(None, a, b).ratio() * 100


def _clip(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _dump_details(details: Dict[str, Any]) -> Dict[str, str]:
    dumped: Dict[str, str] = {}
    for key, value in details.items():
        if value is None or value == "":
            continue
        if isinstance(value, (dict, list)):
            dumped[key] = _clip(json.dumps(value, default=str), 160)
        else:
            dumped[key] = _clip(value, 160)
    return dumped


def _source(entry: Dict[str, Any], field_path: str, excerpt: Any = "") -> EvidenceSource:
    data = entry.get("data", {})
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    return EvidenceSource(
        agent=entry.get("agent", ""),
        stream=entry.get("stream", ""),
        session_id=data.get("session_id", ""),
        turn_id=data.get("turn_id", ""),
        field_path=field_path,
        excerpt=_clip(excerpt, 180),
        timestamp=data.get("timestamp")
        or metadata.get("timestamp_utc")
        or metadata.get("processed_at")
        or _now(),
    )


def _source_key(source: EvidenceSource) -> Tuple[str, str, str, str]:
    return (source.agent, source.turn_id, source.field_path, source.excerpt)


class SessionFactGraph:
    def __init__(self):
        self.graph = nx.MultiDiGraph()
        self.nodes_by_id: Dict[str, ClueFactNode] = {}
        self.canonical_index: Dict[str, str] = {}
        self.edge_index: Dict[Tuple[str, str, str], ClueFactEdge] = {}

    def add_node(
        self,
        node_type: str,
        label: str,
        confidence: float,
        source: EvidenceSource,
        details: Optional[Dict[str, Any]] = None,
        canonical_seed: Optional[str] = None,
    ) -> str:
        label = _clip(label, 80) or "Unknown"
        details = _dump_details(details or {})
        norm_label = _norm(canonical_seed or label)
        canonical_key = f"{node_type}:{norm_label or _short_hash(label)}"

        existing_id = self.canonical_index.get(canonical_key)
        if not existing_id and len(norm_label) >= 4:
            existing_id = self._find_fuzzy_match(node_type, label)

        if existing_id:
            self.canonical_index[canonical_key] = existing_id
            self._merge_node(existing_id, label, confidence, source, details)
            return existing_id

        node_id = f"{node_type}_{_short_hash(canonical_key)}"
        now = _now()
        node = ClueFactNode(
            id=node_id,
            type=node_type,
            label=label,
            canonical_key=canonical_key,
            confidence=max(0.0, min(1.0, float(confidence or 0.5))),
            sources=[source],
            details=details,
            created_at=now,
            updated_at=now,
        )
        self.nodes_by_id[node_id] = node
        self.canonical_index[canonical_key] = node_id
        self.graph.add_node(node_id, **node.model_dump())
        return node_id

    def add_edge(
        self,
        source_id: Optional[str],
        target_id: Optional[str],
        edge_type: str,
        confidence: float,
        source: EvidenceSource,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not source_id or not target_id:
            return
        if source_id not in self.nodes_by_id or target_id not in self.nodes_by_id:
            return
        key = (source_id, target_id, edge_type)
        details = _dump_details(details or {})
        if key in self.edge_index:
            edge = self.edge_index[key]
            edge.confidence = max(edge.confidence, float(confidence or 0.5))
            self._merge_sources(edge.sources, [source])
            for k, v in details.items():
                edge.details.setdefault(k, v)
        else:
            edge = ClueFactEdge(
                source=source_id,
                target=target_id,
                type=edge_type,
                confidence=max(0.0, min(1.0, float(confidence or 0.5))),
                sources=[source],
                details=details,
            )
            self.edge_index[key] = edge
        self.graph.add_edge(source_id, target_id, key=edge_type, **self.edge_index[key].model_dump())

    def export(self, debug: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = ClueMapResult(
            nodes=list(self.nodes_by_id.values()),
            edges=list(self.edge_index.values()),
            debug=debug or {},
        )
        return result.model_dump()

    def _find_fuzzy_match(self, node_type: str, label: str) -> Optional[str]:
        threshold = NODE_TYPE_THRESHOLDS.get(node_type, DEFAULT_FUZZY_THRESHOLD)
        cleaned = _clean_text(label)
        if len(_norm(cleaned)) < 4:
            return None
        best_id = None
        best_score = 0.0
        for node_id, node in self.nodes_by_id.items():
            if node.type != node_type:
                continue
            candidate = _clean_text(node.label)
            score = _score(cleaned, candidate)
            if score > best_score:
                best_score = score
                best_id = node_id
        return best_id if best_score >= threshold else None

    def _merge_node(
        self,
        node_id: str,
        label: str,
        confidence: float,
        source: EvidenceSource,
        details: Dict[str, Any],
    ) -> None:
        node = self.nodes_by_id[node_id]
        node.confidence = max(node.confidence, max(0.0, min(1.0, float(confidence or 0.5))))
        self._merge_sources(node.sources, [source])
        for key, value in details.items():
            node.details.setdefault(key, value)
        if len(label) > len(node.label) and not node.label.lower().startswith("unknown"):
            node.label = _clip(label, 80)
        node.updated_at = _now()
        self.graph.add_node(node_id, **node.model_dump())

    @staticmethod
    def _merge_sources(existing: List[EvidenceSource], incoming: Iterable[EvidenceSource]) -> None:
        seen = {_source_key(src) for src in existing}
        for src in incoming:
            key = _source_key(src)
            if key not in seen:
                existing.append(src)
                seen.add(key)


def build_session_fact_graph(entries: List[Dict[str, Any]], session_id: str) -> Dict[str, Any]:
    graph = SessionFactGraph()
    debug: Dict[str, Any] = {
        "session_id": session_id,
        "payload_entries": len(entries),
        "agents_seen": sorted({e.get("agent", "") for e in entries if e.get("agent")}),
    }

    sorted_entries = sorted(entries, key=lambda e: 0 if "path.analysis" in e.get("stream", "") else 1)
    anchors: Dict[str, str] = {}

    for entry in sorted_entries:
        stream = entry.get("stream", "")
        data = entry.get("data", {})
        if "path.analysis" in stream:
            _extract_path(graph, entry, data, anchors)
        elif "weather.forecast" in stream:
            _extract_weather(graph, entry, data, anchors)
        elif "health.assessment" in stream:
            _extract_health(graph, entry, data, anchors)
        elif "history.out" in stream:
            _extract_history(graph, entry, data, anchors)
        elif "interview.analysis" in stream:
            _extract_interview(graph, entry, data, anchors)
        elif "photo.analysis" in stream:
            _extract_photo(graph, entry, data, anchors)

    _add_cross_agent_links(graph, anchors)
    exported = graph.export(debug=debug)
    exported["debug"]["node_count"] = len(exported["nodes"])
    exported["debug"]["edge_count"] = len(exported["edges"])
    return exported


def _extract_path(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    src = _source(entry, "path", data.get("summary", "Path analysis"))
    lkp = data.get("lkp") or {}
    person_class = data.get("person_class") or data.get("person_profile") or "Missing person"
    srk = data.get("search_radius_km") or {}

    person_id = graph.add_node(
        "person",
        person_class,
        0.9,
        src,
        {
            "Profile": data.get("person_profile", ""),
            "Category": data.get("person_class", ""),
            "LKP": _coords(lkp),
            "Search radius p50": f"{srk.get('p50')} km" if srk.get("p50") else "",
            "Search radius p95": f"{srk.get('p95')} km" if srk.get("p95") else "",
        },
        canonical_seed="missing person",
    )
    anchors["person"] = person_id

    lkp_id = None
    if lkp.get("lat") is not None and lkp.get("lon") is not None:
        lkp_id = graph.add_node(
            "location",
            f"LKP {_coords(lkp)}",
            0.85,
            _source(entry, "lkp", lkp),
            {"Coordinates": _coords(lkp), "Type": "Last known position"},
            canonical_seed=f"lkp:{round(float(lkp.get('lat')), 4)}:{round(float(lkp.get('lon')), 4)}",
        )
        anchors["lkp"] = lkp_id
        graph.add_edge(person_id, lkp_id, "originates_from", 0.85, src)

    for idx, pp in enumerate((data.get("probability_points") or [])[:8]):
        prob = float(pp.get("endpoint_probability") or pp.get("visit_density") or 0.0)
        if prob < 0.03:
            continue
        area_src = _source(entry, f"probability_points[{idx}]", pp)
        area_id = graph.add_node(
            "search_area",
            f"Search area {idx + 1} ({float(pp.get('lat', 0)):.3f}, {float(pp.get('lon', 0)):.3f})",
            min(max(prob, 0.35), 0.95),
            area_src,
            {
                "Probability": f"{round(prob * 100, 1)}%",
                "Coordinates": f"{pp.get('lat')}, {pp.get('lon')}",
                "Rank": pp.get("rank", idx + 1),
            },
            canonical_seed=f"search_area:{round(float(pp.get('lat', 0)), 4)}:{round(float(pp.get('lon', 0)), 4)}",
        )
        anchors.setdefault("search_area", area_id)
        graph.add_edge(person_id, area_id, "predicted_at", min(max(prob, 0.35), 0.95), area_src)
        if lkp_id:
            graph.add_edge(lkp_id, area_id, "projects_to", 0.65, area_src)


def _extract_weather(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    forecasts = data.get("forecasts") or []
    src = _source(entry, "weather", forecasts[0] if forecasts else data.get("daily_summary", data))
    if forecasts:
        f0 = forecasts[0]
        label = f0.get("shortForecast") or f0.get("short_forecast") or "Weather conditions"
        details = {
            "Temperature": f"{f0.get('temperature', '')}{f0.get('temperatureUnit') or f0.get('temperature_unit', '')}",
            "Wind": f0.get("windSpeed") or f0.get("wind_speed", ""),
            "Period": f0.get("name", ""),
        }
    else:
        daily = data.get("daily_summary") or {}
        label = daily.get("conditions") or "Weather conditions"
        details = {
            "Max temp": daily.get("max_temp_c"),
            "Max wind": daily.get("max_wind_kmh"),
            "Precipitation": daily.get("total_precip_mm"),
        }
    weather_id = graph.add_node("weather", label, 0.82, src, details, canonical_seed=f"weather:{label}")
    anchors["weather"] = weather_id
    for anchor_key in ("search_area", "lkp"):
        if anchors.get(anchor_key):
            graph.add_edge(weather_id, anchors[anchor_key], "affects", 0.62, src)

    hourly = data.get("hourly_breakdown") or []
    if hourly:
        worst = max(hourly, key=lambda h: (h.get("max_wind_kmh") or 0) + (h.get("total_precip_mm") or 0) * 2)
        wind = float(worst.get("max_wind_kmh") or 0)
        rain = float(worst.get("total_precip_mm") or 0)
        if wind > 30 or rain > 5:
            hazard_label = f"Wind {wind:.0f} km/h" if wind >= rain * 2 else f"Rain {rain:.1f} mm"
            hazard_id = graph.add_node(
                "clue",
                hazard_label,
                0.72,
                _source(entry, "hourly_breakdown", worst),
                {"Period": worst.get("period", ""), "Wind": wind, "Precipitation": rain},
                canonical_seed=f"weather hazard:{hazard_label}",
            )
            graph.add_edge(weather_id, hazard_id, "includes", 0.72, src)


def _extract_health(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    assessment = data.get("assessment") if isinstance(data.get("assessment"), dict) else data
    risk_level = assessment.get("risk_level") or assessment.get("overall_risk") or ""
    if not risk_level:
        return
    src = _source(entry, "assessment", assessment)
    risks = assessment.get("primary_health_risks") or assessment.get("risks") or []
    actions = assessment.get("recommended_actions") or []
    health_id = graph.add_node(
        "event",
        f"Health risk: {risk_level}",
        0.8,
        src,
        {"Risk level": risk_level, "Action": actions[0] if actions else ""},
        canonical_seed=f"health risk:{risk_level}",
    )
    anchors["health"] = health_id
    if anchors.get("person"):
        graph.add_edge(health_id, anchors["person"], "affects", 0.75, src)

    severity_conf = {"CRITICAL": 0.9, "HIGH": 0.78, "MEDIUM": 0.62, "LOW": 0.45}
    for idx, risk in enumerate(risks[:6]):
        if not isinstance(risk, dict):
            risk = {"condition": str(risk)}
        condition = risk.get("condition") or risk.get("name") or ""
        if not condition:
            continue
        severity = risk.get("severity", "")
        conf = severity_conf.get(str(severity).upper(), 0.65)
        risk_id = graph.add_node(
            "clue",
            f"{condition} {severity}".strip(),
            conf,
            _source(entry, f"primary_health_risks[{idx}]", risk),
            {"Condition": condition, "Severity": severity, "Reasoning": risk.get("reasoning", "")},
            canonical_seed=f"health:{condition}",
        )
        graph.add_edge(health_id, risk_id, "has_risk", conf, src)


def _extract_history(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    matches = data.get("matched_cases") or []
    src = _source(entry, "history", data.get("summary", data.get("actions", "")))
    matches_found = int(data.get("matches_found") or len(matches) or 0)
    hist_id = graph.add_node(
        "event",
        f"{matches_found} similar cases" if matches_found else "Historical analysis",
        0.62,
        src,
        {"Cases matched": matches_found, "Recommendation": data.get("actions", "")},
        canonical_seed="historical analysis",
    )
    anchors["history"] = hist_id
    if anchors.get("person"):
        graph.add_edge(hist_id, anchors["person"], "matched_by_profile", 0.55, src)
    if anchors.get("search_area"):
        graph.add_edge(hist_id, anchors["search_area"], "similar_outcome", 0.5, src)

    for idx, case in enumerate(matches[:6]):
        if not isinstance(case, dict):
            continue
        outcome = _case_value(case, "Incident.Outcome", "Incident_Outcome", "outcome")
        terrain = _case_value(case, "Terrain", "terrain")
        category = _case_value(case, "Subject.Category", "Subject_Category", "category")
        activity = _case_value(case, "Subject.Activity", "Subject_Activity", "activity")
        label_parts = [p for p in [outcome, terrain, category] if p]
        label = " / ".join(label_parts[:2]) or f"Historical case {idx + 1}"
        case_id = graph.add_node(
            "event",
            label,
            0.75 if idx == 0 else 0.65,
            _source(entry, f"matched_cases[{idx}]", case),
            {"Outcome": outcome, "Terrain": terrain, "Category": category, "Activity": activity},
            canonical_seed=f"history:{outcome}:{terrain}:{category}:{activity}:{idx}",
        )
        graph.add_edge(case_id, hist_id, "similar_to", 0.72 if idx == 0 else 0.62, src)
        if anchors.get("search_area") and terrain:
            graph.add_edge(case_id, anchors["search_area"], "historically_found_near", 0.48, src)


def _extract_interview(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else data
    witness = data.get("witness_name") or "Witness report"
    witness_id = graph.add_node(
        "event",
        witness,
        0.72,
        _source(entry, "interview", analysis.get("summary", "")),
        {"Summary": analysis.get("summary", "")},
        canonical_seed=f"witness:{witness}",
    )
    anchors["interview"] = witness_id

    last_location_id = None
    for idx, extraction in enumerate((analysis.get("entity_extraction") or [])[:10]):
        entities = extraction.get("entities") or {}
        section = extraction.get("section", "")
        src = _source(entry, f"entity_extraction[{idx}]", section)
        for person in _as_list(entities.get("people"))[:4]:
            pid = graph.add_node("person", person, 0.7, src, {"Mentioned in": section}, canonical_seed=person)
            graph.add_edge(witness_id, pid, "reported", 0.65, src)
            if anchors.get("person"):
                graph.add_edge(pid, anchors["person"], "associated_with", 0.55, src)
        for place in _as_list(entities.get("places"))[:5]:
            loc_id = graph.add_node("location", place, 0.72, src, {"Mentioned in": section}, canonical_seed=place)
            last_location_id = loc_id
            graph.add_edge(witness_id, loc_id, "reported_at", 0.68, src)
            if anchors.get("person"):
                graph.add_edge(anchors["person"], loc_id, "last_seen", 0.62, src)
        for time_ref in _as_list(entities.get("times"))[:4]:
            time_id = graph.add_node("time", time_ref, 0.66, src, {"Mentioned in": section}, canonical_seed=time_ref)
            graph.add_edge(witness_id, time_id, "reported_time", 0.62, src)
            if last_location_id:
                graph.add_edge(time_id, last_location_id, "located_at", 0.55, src)

    for idx, section in enumerate((analysis.get("important_sections") or [])[:5]):
        text = section.get("section", "") if isinstance(section, dict) else str(section)
        if not text:
            continue
        conf = min(0.9, max(0.5, float(section.get("importance_score", 6) if isinstance(section, dict) else 6) / 10))
        evidence_id = graph.add_node(
            "clue",
            text[:60],
            conf,
            _source(entry, f"important_sections[{idx}]", text),
            {"Reason": section.get("reason", "") if isinstance(section, dict) else ""},
            canonical_seed=f"interview section:{text[:80]}",
        )
        graph.add_edge(witness_id, evidence_id, "reported", conf, _source(entry, "important_sections", text))


def _extract_photo(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, str]) -> None:
    for idx, det in enumerate((data.get("detections") or [])[:10]):
        if not isinstance(det, dict):
            continue
        cls = det.get("class") or det.get("label") or ""
        if not cls:
            continue
        conf = float(det.get("confidence") or 0.5)
        color = det.get("clothing_color") or det.get("dominant_color") or ""
        node_type = "person" if cls == "person" else "evidence"
        label = f"{color} {cls}".strip().title() if color else f"{cls.title()} detected"
        src = _source(entry, f"detections[{idx}]", det)
        evidence_id = graph.add_node(
            node_type,
            label,
            conf,
            src,
            {"Class": cls, "Hair color": det.get("hair_color", ""), "Clothing": color},
            canonical_seed=f"photo:{cls}:{color}:{det.get('hair_color', '')}:{idx}",
        )
        if anchors.get("person"):
            graph.add_edge(evidence_id, anchors["person"], "evidence_of", conf, src)
        if anchors.get("search_area"):
            graph.add_edge(evidence_id, anchors["search_area"], "found_at", min(conf, 0.7), src)


def _add_cross_agent_links(graph: SessionFactGraph, anchors: Dict[str, str]) -> None:
    weather_id = anchors.get("weather")
    health_id = anchors.get("health")
    if weather_id and health_id:
        source = graph.nodes_by_id[weather_id].sources[0]
        graph.add_edge(weather_id, health_id, "exacerbates", 0.62, source)


def _coords(value: Dict[str, Any]) -> str:
    try:
        return f"{float(value.get('lat')):.4f}, {float(value.get('lon')):.4f}"
    except Exception:
        return ""


def _case_value(case: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in case and case[key] not in (None, ""):
            return str(case[key])
    for key, value in case.items():
        normalized = key.replace("_", ".").lower()
        if any(k.replace("_", ".").lower() == normalized for k in keys):
            return str(value)
    return ""


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []
