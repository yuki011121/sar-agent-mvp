#!/usr/bin/env python3
"""
Knowledge Graph for ClueMeister Agent
In-memory graph backed by NetworkX — replaces the previous Neo4j implementation.
The public API (EntityType, RelationType, Entity, Relation, KnowledgeGraph,
ClueMeisterGraphBuilder) is preserved so all callers work without changes.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import Counter

import networkx as nx

logger = logging.getLogger(__name__)


class EntityType(Enum):
    PERSON = "person"
    LOCATION = "location"
    TIME = "time"
    OBJECT = "object"
    EVENT = "event"
    CLUE = "clue"
    AREA = "area"
    RESOURCE = "resource"
    WEATHER = "weather"
    TERRAIN = "terrain"


class RelationType(Enum):
    SEEN_AT = "seen_at"
    LAST_SEEN = "last_seen"
    TRAVELED_TO = "traveled_to"
    OWNS = "owns"
    WEARS = "wears"
    NEAR = "near"
    BEFORE = "before"
    AFTER = "after"
    SIMILAR_TO = "similar_to"
    CONNECTED_TO = "connected_to"
    FOUND_IN = "found_in"
    REQUIRES = "requires"
    AFFECTED_BY = "affected_by"
    LOCATED_IN = "located_in"


@dataclass
class Entity:
    id: str
    type: EntityType
    name: str
    properties: Dict[str, Any]
    confidence: float = 1.0
    source: str = "unknown"
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


@dataclass
class Relation:
    id: str
    source_entity: str
    target_entity: str
    type: RelationType
    properties: Dict[str, Any]
    confidence: float = 1.0
    source: str = "unknown"
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


def _dict_to_entity(data: Dict[str, Any]) -> Entity:
    """Reconstruct an Entity from a node-attribute dict stored in the graph."""
    raw_type = data.get("type", "event")
    try:
        etype = EntityType(raw_type)
    except ValueError:
        etype = EntityType.EVENT
    return Entity(
        id=data.get("id", ""),
        type=etype,
        name=data.get("name", ""),
        properties=data.get("properties", {}),
        confidence=data.get("confidence", 1.0),
        source=data.get("source", "unknown"),
        timestamp=data.get("timestamp"),
    )


class KnowledgeGraph:
    """In-memory knowledge graph backed by NetworkX MultiDiGraph."""

    def __init__(self, **kwargs):
        # Accept (and ignore) legacy Neo4j connection kwargs for API compatibility.
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        logger.info("KnowledgeGraph initialised (NetworkX in-memory backend)")

    # ── Compatibility shim ────────────────────────────────────────────────────

    @property
    def neo4j_available(self) -> bool:
        return False

    @property
    def neo4j_driver(self):
        raise RuntimeError("Neo4j has been removed; use NetworkX methods instead.")

    def close(self):
        pass

    # ── Write operations ──────────────────────────────────────────────────────

    def add_entity(self, entity: Entity) -> str:
        d = asdict(entity)
        d["type"] = entity.type.value  # store string for easy filtering
        self._g.add_node(entity.id, **d)
        return entity.id

    def add_relation(self, relation: Relation) -> str:
        d = asdict(relation)
        d["type"] = relation.type.value
        self._g.add_edge(
            relation.source_entity,
            relation.target_entity,
            key=relation.id,
            **d,
        )
        return relation.id

    # ── Read operations ───────────────────────────────────────────────────────

    def find_entities(
        self,
        entity_type: EntityType = None,
        properties: Dict[str, Any] = None,
        **kwargs,
    ) -> List[Entity]:
        results = []
        type_val = entity_type.value if entity_type else None
        for nid, data in self._g.nodes(data=True):
            if type_val and data.get("type") != type_val:
                continue
            if properties:
                if not all(data.get(k) == v for k, v in properties.items()):
                    continue
            results.append(_dict_to_entity(data))
        return results

    def find_relations(
        self,
        relation_type: RelationType = None,
        source_entity: str = None,
        target_entity: str = None,
        **kwargs,
    ) -> List[Relation]:
        results = []
        type_val = relation_type.value if relation_type else None
        for src, tgt, key, data in self._g.edges(keys=True, data=True):
            if type_val and data.get("type") != type_val:
                continue
            if source_entity and src != source_entity:
                continue
            if target_entity and tgt != target_entity:
                continue
            raw_rtype = data.get("type", "connected_to")
            try:
                rtype = RelationType(raw_rtype)
            except ValueError:
                rtype = RelationType.CONNECTED_TO
            results.append(Relation(
                id=key,
                source_entity=src,
                target_entity=tgt,
                type=rtype,
                properties=data.get("properties", {}),
                confidence=data.get("confidence", 1.0),
                source=data.get("source", "unknown"),
                timestamp=data.get("timestamp"),
            ))
        return results

    def get_entity_neighbors(
        self,
        entity_id: str,
        relation_type: RelationType = None,
        direction: str = "out",
        **kwargs,
    ) -> List[str]:
        if entity_id not in self._g:
            return []
        type_val = relation_type.value if relation_type else None
        neighbors: List[str] = []
        if direction in ("out", "both"):
            for _, tgt, data in self._g.out_edges(entity_id, data=True):
                if type_val and data.get("type") != type_val:
                    continue
                neighbors.append(tgt)
        if direction in ("in", "both"):
            for src, _, data in self._g.in_edges(entity_id, data=True):
                if type_val and data.get("type") != type_val:
                    continue
                neighbors.append(src)
        return neighbors

    def find_paths(
        self,
        source_entity: str,
        target_entity: str,
        max_length: int = 3,
        **kwargs,
    ) -> List[List[str]]:
        try:
            return list(
                nx.all_simple_paths(self._g, source_entity, target_entity, cutoff=max_length)
            )
        except (nx.NodeNotFound, nx.NetworkXError):
            return []

    def calculate_entity_importance(self, entity_id: str) -> float:
        if entity_id not in self._g:
            return 0.0
        degree = self._g.degree(entity_id)
        confidence = self._g.nodes[entity_id].get("confidence", 0.5)
        return float(degree) * confidence

    def find_clusters(self) -> List[List[str]]:
        undirected = self._g.to_undirected()
        return [list(c) for c in nx.connected_components(undirected)]

    def extract_timeline(self) -> List[Dict[str, Any]]:
        entities = [
            data for _, data in self._g.nodes(data=True) if data.get("timestamp")
        ]
        return sorted(entities, key=lambda x: x.get("timestamp", ""))

    def generate_insights(self) -> Dict[str, Any]:
        type_counts = Counter(
            d.get("type") for _, d in self._g.nodes(data=True)
        )
        rel_counts = Counter(
            d.get("type") for _, _, d in self._g.edges(data=True)
        )
        clusters = self.find_clusters()
        important = sorted(
            [
                {
                    "id": n,
                    "importance": self.calculate_entity_importance(n),
                    "confidence": self._g.nodes[n].get("confidence", 0.0),
                    "name": self._g.nodes[n].get("name", n),
                }
                for n in self._g.nodes()
            ],
            key=lambda x: x["importance"],
            reverse=True,
        )[:10]
        return {
            "total_entities": self._g.number_of_nodes(),
            "total_relations": self._g.number_of_edges(),
            "entity_types": dict(type_counts),
            "relation_types": dict(rel_counts),
            "clusters": len(clusters),
            "most_important_entities": important,
        }

    def export_visualization_data(self, output_format: str = "json") -> Dict[str, Any]:
        nodes = [
            {"id": n, **{k: v for k, v in d.items() if k != "properties"}}
            for n, d in self._g.nodes(data=True)
        ]
        edges = [
            {"source": src, "target": tgt, **{k: v for k, v in d.items()}}
            for src, tgt, d in self._g.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}

    def export_graph(self) -> Dict[str, Any]:
        return self.export_visualization_data()

    def import_graph(self, data: Dict[str, Any]) -> bool:
        try:
            for node in data.get("nodes", []):
                self._g.add_node(node["id"], **node)
            for edge in data.get("edges", []):
                self._g.add_edge(edge["source"], edge["target"], **edge)
            return True
        except Exception as e:
            logger.error(f"import_graph failed: {e}")
            return False


class ClueMeisterGraphBuilder:
    """Convenience builder that wraps KnowledgeGraph with SAR-specific helpers."""

    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.entity_counter = 0
        self.relation_counter = 0

    def _generate_id(self, prefix: str) -> str:
        self.entity_counter += 1
        return f"{prefix}_{self.entity_counter}_{int(datetime.utcnow().timestamp())}"

    def _generate_relation_id(self, prefix: str) -> str:
        self.relation_counter += 1
        return f"{prefix}_rel_{self.relation_counter}_{int(datetime.utcnow().timestamp())}"

    def add_missing_person(self, person_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("person"),
            type=EntityType.PERSON,
            name=person_data.get("name", "Unknown Person"),
            properties={
                "age": person_data.get("age"),
                "gender": person_data.get("gender"),
                "height": person_data.get("height"),
                "weight": person_data.get("weight"),
                "hair_color": person_data.get("hair_color"),
                "eye_color": person_data.get("eye_color"),
                "clothing": person_data.get("clothing", []),
                "medical_conditions": person_data.get("medical_conditions", []),
                "last_known_location": person_data.get("last_known_location"),
                "last_seen_time": person_data.get("last_seen_time"),
                "description": person_data.get("description", ""),
            },
            confidence=person_data.get("confidence", 1.0),
            source=person_data.get("source", "unknown"),
        )
        return self.kg.add_entity(entity)

    def add_location(self, location_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("location"),
            type=EntityType.LOCATION,
            name=location_data.get("name", "Unknown Location"),
            properties={
                "coordinates": location_data.get("coordinates"),
                "address": location_data.get("address"),
                "terrain_type": location_data.get("terrain_type"),
                "accessibility": location_data.get("accessibility"),
                "landmarks": location_data.get("landmarks", []),
                "description": location_data.get("description", ""),
            },
            confidence=location_data.get("confidence", 1.0),
            source=location_data.get("source", "unknown"),
        )
        return self.kg.add_entity(entity)

    def add_clue(self, clue_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("clue"),
            type=EntityType.CLUE,
            name=clue_data.get("name", "Unknown Clue"),
            properties={
                "type": clue_data.get("type"),
                "description": clue_data.get("description", ""),
                "found_location": clue_data.get("found_location"),
                "found_time": clue_data.get("found_time"),
                "reliability": clue_data.get("reliability", "unknown"),
                "source": clue_data.get("source", "unknown"),
                "details": clue_data.get("details", {}),
            },
            confidence=clue_data.get("confidence", 1.0),
            source=clue_data.get("source", "unknown"),
        )
        return self.kg.add_entity(entity)

    def add_witness_report(self, witness_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("witness"),
            type=EntityType.PERSON,
            name=witness_data.get("name", "Unknown Witness"),
            properties={
                "report": witness_data.get("report", ""),
                "confidence_level": witness_data.get("confidence_level", "unknown"),
                "location": witness_data.get("location"),
                "time": witness_data.get("time"),
                "details": witness_data.get("details", {}),
            },
            confidence=witness_data.get("confidence", 1.0),
            source=witness_data.get("source", "unknown"),
        )
        return self.kg.add_entity(entity)

    def add_photo_analysis(self, photo_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("photo"),
            type=EntityType.CLUE,
            name=f"Photo Analysis: {photo_data.get('filename', 'unknown')}",
            properties={
                "filename": photo_data.get("filename"),
                "detections": photo_data.get("detections", []),
                "person_analysis": photo_data.get("person_analysis", {}),
                "sar_context": photo_data.get("sar_context", {}),
                "location": photo_data.get("location"),
                "timestamp": photo_data.get("timestamp"),
                "analysis_confidence": photo_data.get("analysis_confidence", 0.5),
            },
            confidence=photo_data.get("confidence", 1.0),
            source=photo_data.get("source", "photo_analysis"),
        )
        return self.kg.add_entity(entity)

    def add_historical_case(self, case_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("case"),
            type=EntityType.EVENT,
            name=f"Historical Case: {case_data.get('case_id', 'unknown')}",
            properties={
                "case_id": case_data.get("case_id"),
                "outcome": case_data.get("outcome"),
                "similarity_score": case_data.get("similarity_score"),
                "key_factors": case_data.get("key_factors", []),
                "lessons_learned": case_data.get("lessons_learned", []),
                "recommendations": case_data.get("recommendations", []),
            },
            confidence=case_data.get("confidence", 1.0),
            source=case_data.get("source", "history_agent"),
        )
        return self.kg.add_entity(entity)

    def add_weather_condition(self, weather_data: Dict[str, Any]) -> str:
        entity = Entity(
            id=self._generate_id("weather"),
            type=EntityType.WEATHER,
            name=f"Weather: {weather_data.get('condition', 'unknown')}",
            properties={
                "condition": weather_data.get("condition"),
                "temperature": weather_data.get("temperature"),
                "wind_speed": weather_data.get("wind_speed"),
                "visibility": weather_data.get("visibility"),
                "forecast": weather_data.get("forecast", {}),
                "impact_on_search": weather_data.get("impact_on_search", "unknown"),
            },
            confidence=weather_data.get("confidence", 1.0),
            source=weather_data.get("source", "weather_agent"),
        )
        return self.kg.add_entity(entity)

    def link_entities(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        properties: Dict[str, Any] = None,
        confidence: float = 1.0,
        source: str = "unknown",
    ) -> str:
        relation = Relation(
            id=self._generate_relation_id("link"),
            source_entity=source_id,
            target_entity=target_id,
            type=relation_type,
            properties=properties or {},
            confidence=confidence,
            source=source,
        )
        return self.kg.add_relation(relation)

    def build_relationships_from_data(self, entities: List[str], data: Dict[str, Any]):
        """Auto-build relationships (no-op; kept for API compatibility)."""
        pass
