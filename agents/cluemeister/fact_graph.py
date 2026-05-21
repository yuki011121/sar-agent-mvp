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
    priority_score: float = 0.0
    priority_tier: str = "low"
    rank: Optional[int] = None
    sources: List[EvidenceSource] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    role: str = "context"
    display_label: str = ""
    detail_label: str = ""
    decision_tier: str = "support"
    priority_rank: Optional[int] = None
    geo: Optional[Dict[str, float]] = None
    support_summary: str = ""
    created_at: str = ""
    updated_at: str = ""


class ClueFactEdge(BaseModel):
    id: str = ""
    source: str
    target: str
    type: str
    confidence: float = 0.5
    sources: List[EvidenceSource] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    importance: str = "context"
    display_label: str = ""
    show_in_command: bool = False
    show_in_analyze: bool = True


class ClueMapResult(BaseModel):
    schema_version: str = "decision_map_v2"
    views: Dict[str, Any] = Field(default_factory=dict)
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
            dumped[key] = _clip(json.dumps(value, default=str), 600)
        else:
            dumped[key] = _clip(value, 600)
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
        excerpt=_clip(excerpt, 420),
        timestamp=data.get("timestamp")
        or metadata.get("timestamp_utc")
        or metadata.get("processed_at")
        or _now(),
    )


def _source_key(source: EvidenceSource) -> Tuple[str, str, str, str]:
    return (source.agent, source.turn_id, source.field_path, source.excerpt)


def _priority_tier(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _severity_weight(node: ClueFactNode) -> float:
    text = " ".join(str(v) for v in [node.label, *node.details.values()]).lower()
    if "critical" in text:
        return 1.0
    if "high" in text or "diabetic" in text or "hypothermia" in text or "exposure" in text:
        return 0.8
    if "medium" in text or "dehydration" in text:
        return 0.55
    if "low" in text:
        return 0.3
    return 0.45 if node.type in ("clue", "event", "weather", "search_area") else 0.25


def _actionability_weight(node: ClueFactNode) -> float:
    details_text = " ".join(str(v) for v in node.details.values()).lower()
    if node.type == "search_area":
        return 1.0
    if any(k in details_text for k in ("action", "recommend", "coordinate", "probability", "lkp")):
        return 0.85
    if node.type in ("clue", "weather", "location", "evidence"):
        return 0.65
    if node.type == "event":
        return 0.55
    return 0.35


def _payload_debug(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    shapes: Dict[str, Any] = {}
    for entry in entries:
        agent = entry.get("agent") or entry.get("stream", "unknown").split(".")[0] or "unknown"
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        info = shapes.setdefault(agent, {"entries": 0, "keys": []})
        info["entries"] += 1
        info["keys"] = sorted(set(info["keys"]) | set(data.keys()))
        if "history.out" in entry.get("stream", ""):
            matches = _history_matches(data)
            info["matches_found"] = int(data.get("matches_found") or len(matches) or 0)
            info["matched_cases_count"] = len(matches)
            if info["matches_found"] and not matches:
                info["warning"] = "case details unavailable from history payload"
        elif "health.assessment" in entry.get("stream", ""):
            assessment = data.get("assessment") if isinstance(data.get("assessment"), dict) else data
            info["risks_count"] = len(assessment.get("primary_health_risks") or assessment.get("risks") or [])
        elif "weather.forecast" in entry.get("stream", ""):
            info["has_forecast"] = bool(data.get("forecasts") or data.get("daily_summary"))
    return shapes


PRIMARY_EDGE_TYPES = {
    "involves",
    "originates_from",
    "predicted_at",
    "projects_to",
    "has_risk",
    "affects",
}

SUPPORTING_EDGE_TYPES = {
    "last_seen",
    "evidence_of",
    "found_at",
    "matched_by_profile",
    "similar_outcome",
    "historically_found_near",
    "supports_risk",
    "exacerbates",
    "associated_with",
    "reported_at",
}

ROLE_LABELS = {
    "incident": "Current incident",
    "subject": "Subject profile",
    "lkp": "Last known position",
    "search_area": "Search area",
    "risk": "Risk",
    "evidence": "Evidence",
    "history": "Historical support",
    "context": "Context",
}


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _parse_geo(*values: Any) -> Optional[Dict[str, float]]:
    text = " ".join(str(value) for value in values if value not in (None, ""))
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", text)
    if not match:
        return None
    lat = _as_float(match.group(1))
    lon = _as_float(match.group(2))
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {"lat": lat, "lon": lon}


def _source_summary(sources: List[EvidenceSource]) -> str:
    agents = []
    for source in sources:
        agent = source.agent or source.stream.split(".")[0] or "source"
        if agent and agent not in agents:
            agents.append(agent)
    if not agents:
        return "No source metadata"
    label = ", ".join(agents[:3])
    if len(agents) > 3:
        label += f" +{len(agents) - 3}"
    return f"Supported by {label}"


def _rank_value(node: ClueFactNode) -> Optional[int]:
    raw = node.details.get("Rank")
    try:
        return int(raw)
    except Exception:
        return None


def _display_label_for(node: ClueFactNode, role: str) -> str:
    label = node.label.replace("_", " ").strip()
    if role == "incident":
        return "Current incident"
    if role == "subject":
        return f"Subject: {_clip(label, 24)}" if label else "Subject profile"
    if role == "lkp":
        return "Last known position"
    if role == "search_area":
        rank = _rank_value(node)
        return f"Search area {rank}" if rank else "Search area"
    if role == "risk":
        if label.lower().startswith("health risk:"):
            condition = "Overall health risk"
        else:
            condition = node.details.get("Condition") or label.replace("Health risk:", "").strip()
        severity = node.details.get("Severity") or node.details.get("Risk level")
        if condition and severity and str(severity).lower() not in str(condition).lower():
            return _clip(f"{condition} ({severity})", 32)
        return _clip(condition or label or "Risk", 32)
    if role == "history":
        return _clip(label or "Historical support", 30)
    if role == "evidence":
        return _clip(label or "Evidence", 30)
    return _clip(label or ROLE_LABELS.get(role, "Context"), 30)


def _role_for_node(node: ClueFactNode) -> str:
    details_text = " ".join(str(v) for v in node.details.values()).lower()
    label_text = node.label.lower()
    key = node.canonical_key.lower()
    if "currentincident" in key or node.details.get("Role") == "Session anchor":
        return "incident"
    if node.type == "person" and ("missingperson" in key or node.details.get("Category") or node.details.get("Profile")):
        return "subject"
    if node.type == "location" and ("lkp" in key or "last known position" in details_text or label_text.startswith("lkp")):
        return "lkp"
    if node.type == "search_area":
        return "search_area"
    if node.details.get("Condition") or node.details.get("Severity") or node.details.get("Risk level") or label_text.startswith("health risk:"):
        return "risk"
    if "historical" in label_text or "history" in key or "similar cases" in label_text:
        return "history"
    if node.type in ("clue", "evidence"):
        return "evidence"
    return "context"


def _decision_tier_for(node: ClueFactNode, role: str) -> str:
    if role in {"evidence", "history", "context"}:
        return "support"
    severity = str(node.details.get("Severity") or node.details.get("Risk level") or "").lower()
    if "critical" in severity:
        return "critical"
    if "high" in severity and role == "risk":
        return "high"
    return node.priority_tier if node.priority_tier in {"critical", "high", "medium", "low"} else "low"


def _edge_importance(edge: ClueFactEdge, nodes_by_id: Dict[str, ClueFactNode]) -> str:
    if edge.type in PRIMARY_EDGE_TYPES:
        return "primary"
    if edge.type in SUPPORTING_EDGE_TYPES:
        return "supporting"
    source = nodes_by_id.get(edge.source)
    target = nodes_by_id.get(edge.target)
    roles = {source.role if source else "", target.role if target else ""}
    if "risk" in roles and edge.confidence >= 0.58:
        return "supporting"
    return "context"


def _edge_display_label(edge_type: str) -> str:
    labels = {
        "involves": "involves",
        "originates_from": "starts at",
        "predicted_at": "projected to",
        "projects_to": "projects to",
        "has_risk": "has risk",
        "affects": "affects",
        "exacerbates": "worsens",
        "supports_risk": "supports risk",
        "matched_by_profile": "profile match",
        "similar_outcome": "similar outcome",
        "historically_found_near": "history near",
        "evidence_of": "evidence of",
        "found_at": "found at",
        "last_seen": "last seen",
    }
    return labels.get(edge_type, edge_type.replace("_", " "))


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
        reason: str = "",
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
            if reason and not edge.reason:
                edge.reason = _clip(reason, 300)
        else:
            edge_id = f"edge_{_short_hash('|'.join(key))}"
            edge = ClueFactEdge(
                id=edge_id,
                source=source_id,
                target=target_id,
                type=edge_type,
                confidence=max(0.0, min(1.0, float(confidence or 0.5))),
                sources=[source],
                details=details,
                reason=_clip(reason, 300),
            )
            self.edge_index[key] = edge
        self.graph.add_edge(source_id, target_id, key=edge_type, **self.edge_index[key].model_dump())

    def export(self, debug: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._apply_priorities()
        self._apply_decision_metadata()
        views = self._build_views()
        result = ClueMapResult(
            views=views,
            nodes=list(self.nodes_by_id.values()),
            edges=list(self.edge_index.values()),
            debug=debug or {},
        )
        return result.model_dump()

    def _apply_priorities(self) -> None:
        neighbor_agents: Dict[str, set[str]] = {node_id: set() for node_id in self.nodes_by_id}
        for node_id, node in self.nodes_by_id.items():
            neighbor_agents[node_id].update(src.agent for src in node.sources if src.agent)
        for edge in self.edge_index.values():
            edge_agents = {src.agent for src in edge.sources if src.agent}
            for endpoint, other in ((edge.source, edge.target), (edge.target, edge.source)):
                if endpoint in neighbor_agents:
                    neighbor_agents[endpoint].update(edge_agents)
                    other_node = self.nodes_by_id.get(other)
                    if other_node:
                        neighbor_agents[endpoint].update(src.agent for src in other_node.sources if src.agent)

        for node_id, node in self.nodes_by_id.items():
            severity = _severity_weight(node)
            cross_agent_support = min(1.0, max(0, len(neighbor_agents.get(node_id, set())) - 1) / 3)
            actionability = _actionability_weight(node)
            source_bonus = min(1.0, len(node.sources) / 3)
            score = (
                node.confidence * 35
                + severity * 25
                + cross_agent_support * 20
                + actionability * 15
                + source_bonus * 5
            )
            node.priority_score = round(score, 1)
            node.priority_tier = _priority_tier(score)
            node.details.setdefault("Priority score", node.priority_score)
            node.details.setdefault("Priority tier", node.priority_tier)

        ranked = sorted(self.nodes_by_id.values(), key=lambda n: n.priority_score, reverse=True)
        for idx, node in enumerate(ranked, start=1):
            node.rank = idx
            self.graph.add_node(node.id, **node.model_dump())

    def _apply_decision_metadata(self) -> None:
        for node in self.nodes_by_id.values():
            role = _role_for_node(node)
            node.role = role
            node.detail_label = node.label
            node.display_label = _display_label_for(node, role)
            node.decision_tier = _decision_tier_for(node, role)
            node.priority_rank = _rank_value(node) if role == "search_area" else (
                node.rank if role == "risk" and node.rank and node.rank <= 9 else None
            )
            node.geo = _parse_geo(node.details.get("Coordinates"), node.label) if role in {"lkp", "search_area"} else None
            node.support_summary = _source_summary(node.sources)
            self.graph.add_node(node.id, **node.model_dump())

        for edge in self.edge_index.values():
            edge.importance = _edge_importance(edge, self.nodes_by_id)
            edge.display_label = _edge_display_label(edge.type)
            edge.show_in_analyze = True
            edge.show_in_command = False
            self.graph.add_edge(edge.source, edge.target, key=edge.type, **edge.model_dump())

    def _build_views(self) -> Dict[str, Any]:
        all_node_ids = set(self.nodes_by_id.keys())
        all_edge_ids = {edge.id for edge in self.edge_index.values()}
        command_node_ids = self._command_node_ids()
        command_edge_ids = {
            edge.id
            for edge in self.edge_index.values()
            if edge.source in command_node_ids
            and edge.target in command_node_ids
            and edge.importance in {"primary", "supporting"}
        }

        for edge in self.edge_index.values():
            edge.show_in_command = edge.id in command_edge_ids
            edge.show_in_analyze = True

        return {
            "command": {
                "node_ids": sorted(command_node_ids),
                "edge_ids": sorted(command_edge_ids),
                "hidden_counts": {
                    "nodes": max(0, len(all_node_ids) - len(command_node_ids)),
                    "edges": max(0, len(all_edge_ids) - len(command_edge_ids)),
                },
                "focus": "decision",
            },
            "analyze": {
                "node_ids": sorted(all_node_ids),
                "edge_ids": sorted(all_edge_ids),
                "hidden_counts": {"nodes": 0, "edges": 0},
                "focus": "evidence",
            },
        }

    def _command_node_ids(self) -> set[str]:
        selected: set[str] = {
            node.id
            for node in self.nodes_by_id.values()
            if node.role in {"incident", "subject", "lkp"}
        }

        def by_decision(node: ClueFactNode) -> Tuple[int, float, float]:
            tier_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "support": 0}
            rank_bonus = 1 / max(1, node.priority_rank or node.rank or 99)
            return (tier_weight.get(node.decision_tier, 0), node.priority_score, rank_bonus)

        search_areas = sorted(
            [node for node in self.nodes_by_id.values() if node.role == "search_area"],
            key=lambda n: (_rank_value(n) or 999, -n.priority_score),
        )
        risks = sorted(
            [node for node in self.nodes_by_id.values() if node.role == "risk"],
            key=by_decision,
            reverse=True,
        )
        selected.update(node.id for node in search_areas[:3])
        selected.update(node.id for node in risks[:3])

        # Add a small number of operational connector nodes for selected risks,
        # without expanding from a connector into every adjacent support node.
        for edge in self.edge_index.values():
            if edge.importance not in {"primary", "supporting"}:
                continue
            if edge.target in selected and edge.source not in selected:
                source = self.nodes_by_id.get(edge.source)
                if source and source.role in {"risk", "subject", "incident"}:
                    selected.add(edge.source)
            if edge.source in selected and edge.target not in selected:
                target = self.nodes_by_id.get(edge.target)
                if target and target.role in {"subject", "incident", "lkp"}:
                    selected.add(edge.target)

        if not selected and self.nodes_by_id:
            selected.add(max(self.nodes_by_id.values(), key=lambda n: n.priority_score).id)
        return selected

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
        "payload_shapes": _payload_debug(entries),
    }

    sorted_entries = sorted(entries, key=lambda e: 0 if "path.analysis" in e.get("stream", "") else 1)
    anchors: Dict[str, Any] = {}
    incident_src = EvidenceSource(
        agent="cluemeister",
        stream="cluemeister.session",
        session_id=session_id,
        field_path="session",
        excerpt="Session-level anchor for correlated SAR clues",
        timestamp=_now(),
    )
    anchors["incident"] = graph.add_node(
        "event",
        "Current incident",
        0.72,
        incident_src,
        {"Session ID": session_id, "Role": "Session anchor"},
        canonical_seed=f"current incident:{session_id}",
    )

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
    linked_ids = {e["source"] for e in exported["edges"]} | {e["target"] for e in exported["edges"]}
    exported["debug"]["unlinked_node_count"] = len([n for n in exported["nodes"] if n["id"] not in linked_ids])
    return exported


def _extract_path(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
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
    graph.add_edge(
        anchors.get("incident"),
        person_id,
        "involves",
        0.85,
        src,
        reason="Path analysis identifies the missing subject profile for this incident.",
    )

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
        graph.add_edge(person_id, lkp_id, "originates_from", 0.85, src, reason="LKP is the starting point for path analysis.")

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
        graph.add_edge(person_id, area_id, "predicted_at", min(max(prob, 0.35), 0.95), area_src, reason="Monte Carlo path analysis ranks this search area.")
        if lkp_id:
            graph.add_edge(lkp_id, area_id, "projects_to", 0.65, area_src, reason="Search area is projected from the last known position.")


def _extract_weather(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
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
    connected = False
    for anchor_key in ("search_area", "lkp"):
        if anchors.get(anchor_key):
            graph.add_edge(weather_id, anchors[anchor_key], "affects", 0.62, src, reason="Weather conditions affect field operations at this location.")
            connected = True
    if not connected and anchors.get("incident"):
        graph.add_edge(weather_id, anchors["incident"], "affects", 0.58, src, reason="Weather is relevant to the current incident even without a mapped search area.")

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
            graph.add_edge(weather_id, hazard_id, "includes", 0.72, src, reason="Forecast details include this operational hazard.")


def _extract_health(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
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
        graph.add_edge(health_id, anchors["person"], "affects", 0.75, src, reason="Health assessment applies to the missing person profile.")
    elif anchors.get("incident"):
        graph.add_edge(health_id, anchors["incident"], "affects", 0.68, src, reason="Health assessment applies to the current incident.")

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
        anchors.setdefault("health_risks", []).append(risk_id)
        graph.add_edge(health_id, risk_id, "has_risk", conf, src, reason="Health agent listed this as a primary health risk.")


def _extract_history(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
    matches = _history_matches(data)
    src = _source(entry, "history", data.get("summary", data.get("actions", "")))
    matches_found = int(data.get("matches_found") or len(matches) or 0)
    details: Dict[str, Any] = {"Cases matched": matches_found, "Recommendation": data.get("actions", "")}
    if matches_found and not matches:
        details["Case details"] = "Case details unavailable from history payload"
    hist_id = graph.add_node(
        "event",
        "Historical patterns" if matches else (f"{matches_found} similar cases" if matches_found else "Historical analysis"),
        0.62,
        src,
        details,
        canonical_seed="historical analysis",
    )
    anchors["history"] = hist_id
    if anchors.get("person"):
        graph.add_edge(hist_id, anchors["person"], "matched_by_profile", 0.55, src, reason="History search used the current subject profile.")
    elif anchors.get("incident"):
        graph.add_edge(hist_id, anchors["incident"], "corroborates", 0.52, src, reason="Historical analysis provides precedent for the current incident.")
    if anchors.get("search_area"):
        graph.add_edge(hist_id, anchors["search_area"], "similar_outcome", 0.5, src, reason="Historical patterns inform prioritization of the current search area.")

    for idx, case in enumerate(matches[:6]):
        if not isinstance(case, dict):
            continue
        outcome = _case_value(case, "Incident.Outcome", "Incident_Outcome", "outcome")
        terrain = _case_value(case, "Terrain", "terrain")
        category = _case_value(case, "Subject.Category", "Subject_Category", "category")
        activity = _case_value(case, "Subject.Activity", "Subject_Activity", "activity")
        age = _case_value(case, "Age", "age")
        status = _case_value(case, "Subject.Status", "Subject_Status", "status")
        similarity = _case_value(case, "similarity_score", "score", "confidence")
        label_parts = [p for p in [outcome, terrain, category] if p]
        label = " / ".join(label_parts[:2]) or f"Historical case {idx + 1}"
        case_conf = _case_confidence(similarity, 0.75 if idx == 0 else 0.65)
        case_id = graph.add_node(
            "event",
            label,
            case_conf,
            _source(entry, f"matched_cases[{idx}]", case),
            {
                "Outcome": outcome,
                "Terrain": terrain,
                "Category": category,
                "Activity": activity,
                "Age": age,
                "Status": status,
                "Similarity": similarity,
            },
            canonical_seed=f"history:{outcome}:{terrain}:{category}:{activity}:{age}:{status}:{idx}",
        )
        anchors.setdefault("history_cases", []).append(case_id)
        graph.add_edge(case_id, hist_id, "similar_to", max(0.62, case_conf), src, reason="This ISRID case was retrieved as similar historical precedent.")
        if anchors.get("incident"):
            graph.add_edge(case_id, anchors["incident"], "corroborates", 0.5, src, reason="Historical case provides precedent for the current incident.")
        if anchors.get("search_area") and terrain:
            graph.add_edge(case_id, anchors["search_area"], "historically_found_near", 0.48, src, reason="Historical terrain/activity pattern can inform this search area.")


def _extract_interview(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
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
    if anchors.get("incident"):
        graph.add_edge(witness_id, anchors["incident"], "reported", 0.58, _source(entry, "interview", analysis.get("summary", "")), reason="Witness report belongs to the current incident.")

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
        graph.add_edge(witness_id, evidence_id, "reported", conf, _source(entry, "important_sections", text), reason="Interview analysis marked this section as important.")


def _extract_photo(graph: SessionFactGraph, entry: Dict[str, Any], data: Dict[str, Any], anchors: Dict[str, Any]) -> None:
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
            graph.add_edge(evidence_id, anchors["person"], "evidence_of", conf, src, reason="Photo detection may evidence the missing person or carried item.")
        elif anchors.get("incident"):
            graph.add_edge(evidence_id, anchors["incident"], "evidence_of", min(conf, 0.65), src, reason="Photo detection is evidence attached to the current incident.")
        if anchors.get("search_area"):
            graph.add_edge(evidence_id, anchors["search_area"], "found_at", min(conf, 0.7), src, reason="Photo evidence is associated with the current search area.")


def _add_cross_agent_links(graph: SessionFactGraph, anchors: Dict[str, Any]) -> None:
    weather_id = anchors.get("weather")
    health_id = anchors.get("health")
    if weather_id and health_id:
        source = graph.nodes_by_id[weather_id].sources[0]
        graph.add_edge(
            weather_id,
            health_id,
            "exacerbates",
            0.62,
            source,
            reason="Weather conditions can worsen the overall health risk assessment.",
        )

    if weather_id:
        weather_text = _node_text(graph.nodes_by_id[weather_id])
        weather_source = graph.nodes_by_id[weather_id].sources[0]
        for risk_id in anchors.get("health_risks", []):
            risk = graph.nodes_by_id.get(risk_id)
            if not risk:
                continue
            risk_text = _node_text(risk)
            if _weather_health_match(weather_text, risk_text):
                graph.add_edge(
                    weather_id,
                    risk_id,
                    "exacerbates",
                    0.72,
                    weather_source,
                    reason="Weather keywords match this health risk, increasing operational urgency.",
                )

    for case_id in anchors.get("history_cases", []):
        case = graph.nodes_by_id.get(case_id)
        if not case:
            continue
        case_text = _node_text(case)
        case_source = case.sources[0]
        for risk_id in anchors.get("health_risks", []):
            risk = graph.nodes_by_id.get(risk_id)
            if risk and _history_health_match(case_text, _node_text(risk)):
                graph.add_edge(
                    case_id,
                    risk_id,
                    "supports_risk",
                    0.58,
                    case_source,
                    reason="Historical case attributes overlap with the current health risk.",
                )
        if weather_id and _history_weather_match(case_text, _node_text(graph.nodes_by_id[weather_id])):
            graph.add_edge(
                case_id,
                weather_id,
                "corroborates",
                0.52,
                case_source,
                reason="Historical case terrain or activity overlaps with current weather concerns.",
            )


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


def _history_matches(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("matched_cases", "similar_cases", "matches", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [case for case in value if isinstance(case, dict)]
    return []


def _case_confidence(value: str, default: float) -> float:
    if not value:
        return default
    try:
        score = float(value)
        if score > 1:
            score = score / 100
        return max(0.35, min(0.95, score))
    except Exception:
        return default


def _node_text(node: ClueFactNode) -> str:
    return " ".join(str(v) for v in [node.label, *node.details.values()]).lower()


def _weather_health_match(weather_text: str, risk_text: str) -> bool:
    pairs = (
        (("cold", "wind", "snow", "freez", "frost"), ("hypothermia", "exposure", "frostbite", "diabetic")),
        (("heat", "hot", "sunny", "dry"), ("dehydration", "heat", "diabetic")),
        (("rain", "storm", "precip", "wind"), ("exposure", "hypothermia", "injury")),
    )
    return any(any(w in weather_text for w in ws) and any(r in risk_text for r in rs) for ws, rs in pairs)


def _history_health_match(case_text: str, risk_text: str) -> bool:
    shared_keywords = (
        "diabetic",
        "diabetes",
        "elderly",
        "dementia",
        "dehydration",
        "hypothermia",
        "exposure",
        "mountain",
        "forest",
        "water",
        "trail",
    )
    if any(k in case_text and k in risk_text for k in shared_keywords):
        return True
    age_match = re.search(r"\b([6-9]\d|1\d\d)\b", case_text)
    return bool(age_match and any(k in risk_text for k in ("diabetic", "exposure", "dehydration", "hypothermia")))


def _history_weather_match(case_text: str, weather_text: str) -> bool:
    terrain_terms = ("mountain", "forest", "trail", "water", "urban", "rural", "desert")
    hazard_terms = ("cold", "wind", "snow", "rain", "heat", "hot", "sunny", "storm")
    return any(t in case_text for t in terrain_terms) and any(h in weather_text for h in hazard_terms)


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []
