#!/usr/bin/env python3
"""
Knowledge Graph for ClueMeister Agent
Build and manage knowledge graphs for search and rescue missions
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import networkx as nx
import numpy as np
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)

class EntityType(Enum):
    """Entity type enumeration"""
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
    """Relation type enumeration"""
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
    """Knowledge graph entity"""
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
    """Knowledge graph relation"""
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

class KnowledgeGraph:
    """Search and rescue knowledge graph"""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relations: Dict[str, Relation] = {}
        self.graph = nx.MultiDiGraph()
        self.entity_counter = 0
        self.relation_counter = 0
        
    def add_entity(self, entity: Entity) -> str:
        """Add entity to graph"""
        if entity.id not in self.entities:
            self.entities[entity.id] = entity
            self.graph.add_node(entity.id, **asdict(entity))
            logger.debug(f"Added entity: {entity.id} ({entity.type.value})")
        else:
            existing = self.entities[entity.id]
            existing.properties.update(entity.properties)
            existing.confidence = max(existing.confidence, entity.confidence)
            existing.timestamp = entity.timestamp
            logger.debug(f"Updated entity: {entity.id}")
        
        return entity.id
    
    def add_relation(self, relation: Relation) -> str:
        """Add relation to graph"""
        if relation.id not in self.relations:
            self.relations[relation.id] = relation
            self.graph.add_edge(
                relation.source_entity, 
                relation.target_entity,
                key=relation.id,
                **asdict(relation)
            )
            logger.debug(f"Added relation: {relation.id} ({relation.type.value})")
        else:
            existing = self.relations[relation.id]
            existing.properties.update(relation.properties)
            existing.confidence = max(existing.confidence, relation.confidence)
            existing.timestamp = relation.timestamp
            logger.debug(f"Updated relation: {relation.id}")
        
        return relation.id
    
    def find_entities(self, entity_type: EntityType = None, 
                     properties: Dict[str, Any] = None) -> List[Entity]:
        """Find entities"""
        results = []
        
        for entity in self.entities.values():
            if entity_type and entity.type != entity_type:
                continue
                
            if properties:
                match = True
                for key, value in properties.items():
                    if key not in entity.properties or entity.properties[key] != value:
                        match = False
                        break
                if not match:
                    continue
            
            results.append(entity)
        
        return results
    
    def find_relations(self, relation_type: RelationType = None,
                      source_entity: str = None,
                      target_entity: str = None) -> List[Relation]:
        """Find relations"""
        results = []
        
        for relation in self.relations.values():
            if relation_type and relation.type != relation_type:
                continue
            if source_entity and relation.source_entity != source_entity:
                continue
            if target_entity and relation.target_entity != target_entity:
                continue
            
            results.append(relation)
        
        return results
    
    def get_entity_neighbors(self, entity_id: str, 
                           relation_types: List[RelationType] = None) -> List[Tuple[Entity, Relation]]:
        """Get entity neighbors and relations"""
        neighbors = []
        
        if entity_id not in self.entities:
            return neighbors
        
        for relation in self.relations.values():
            if relation_types and relation.type not in relation_types:
                continue
                
            if relation.source_entity == entity_id:
                target_entity = self.entities.get(relation.target_entity)
                if target_entity:
                    neighbors.append((target_entity, relation))
            elif relation.target_entity == entity_id:
                source_entity = self.entities.get(relation.source_entity)
                if source_entity:
                    neighbors.append((source_entity, relation))
        
        return neighbors
    
    def find_paths(self, source_entity: str, target_entity: str, 
                  max_length: int = 3) -> List[List[str]]:
        """Find paths between two entities"""
        if source_entity not in self.entities or target_entity not in self.entities:
            return []
        
        try:
            paths = list(nx.all_simple_paths(
                self.graph, source_entity, target_entity, cutoff=max_length
            ))
            return paths
        except nx.NetworkXNoPath:
            return []
    
    def calculate_entity_importance(self, entity_id: str) -> float:
        """Calculate entity importance score"""
        if entity_id not in self.entities:
            return 0.0
        
        entity = self.entities[entity_id]
        
        # Base score
        importance = entity.confidence
        
        # Degree score
        degree = self.graph.degree(entity_id)
        importance += degree * 0.1
        
        # Centrality score
        try:
            centrality = nx.betweenness_centrality(self.graph).get(entity_id, 0)
            importance += centrality * 0.5
        except:
            pass
        
        # Type weight
        type_weights = {
            EntityType.PERSON: 2.0,
            EntityType.LOCATION: 1.5,
            EntityType.CLUE: 1.8,
            EntityType.EVENT: 1.3,
            EntityType.OBJECT: 1.0,
            EntityType.TIME: 0.8,
            EntityType.AREA: 1.2,
            EntityType.RESOURCE: 1.1,
            EntityType.WEATHER: 0.9,
            EntityType.TERRAIN: 1.0
        }
        
        importance *= type_weights.get(entity.type, 1.0)
        
        return importance
    
    def find_clusters(self) -> List[List[str]]:
        """Find entity clusters"""
        try:
            # Use weakly connected components
            clusters = list(nx.weakly_connected_components(self.graph))
            return [list(cluster) for cluster in clusters]
        except:
            return []
    
    def extract_timeline(self) -> List[Dict[str, Any]]:
        """Extract timeline"""
        timeline = []
        
        for entity in self.entities.values():
            if entity.type == EntityType.TIME:
                timeline.append({
                    "entity_id": entity.id,
                    "timestamp": entity.properties.get("timestamp"),
                    "description": entity.properties.get("description", entity.name),
                    "confidence": entity.confidence
                })
        
        # Sort by time
        timeline.sort(key=lambda x: x.get("timestamp", ""))
        return timeline
    
    def generate_insights(self) -> Dict[str, Any]:
        """Generate insights"""
        insights = {
            "total_entities": len(self.entities),
            "total_relations": len(self.relations),
            "entity_types": Counter([e.type.value for e in self.entities.values()]),
            "relation_types": Counter([r.type.value for r in self.relations.values()]),
            "clusters": len(self.find_clusters()),
            "timeline_events": len(self.extract_timeline()),
                "most_important_entities": []
            }
        
        # Find most important entities
        entity_importance = {}
        for entity_id in self.entities:
            entity_importance[entity_id] = self.calculate_entity_importance(entity_id)
        
        top_entities = sorted(entity_importance.items(), key=lambda x: x[1], reverse=True)[:5]
        
        for entity_id, importance in top_entities:
            entity = self.entities[entity_id]
            insights["most_important_entities"].append({
                "id": entity_id,
                "name": entity.name,
                "type": entity.type.value,
                "importance": importance,
                "confidence": entity.confidence
            })
        
        return insights
    
    def export_graph(self) -> Dict[str, Any]:
        """Export graph data"""
        return {
            "entities": {eid: asdict(entity) for eid, entity in self.entities.items()},
            "relations": {rid: asdict(relation) for rid, relation in self.relations.items()},
            "insights": self.generate_insights(),
            "export_timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def import_graph(self, data: Dict[str, Any]) -> bool:
        """Import graph data"""
        try:
            # Clear existing data
            self.entities.clear()
            self.relations.clear()
            self.graph.clear()
            
            # Import entities
            for eid, entity_data in data.get("entities", {}).items():
                entity = Entity(**entity_data)
                entity.type = EntityType(entity.type) if isinstance(entity.type, str) else entity.type
                self.add_entity(entity)
            
            # Import relations
            for rid, relation_data in data.get("relations", {}).items():
                relation = Relation(**relation_data)
                relation.type = RelationType(relation.type) if isinstance(relation.type, str) else relation.type
                self.add_relation(relation)
            
            logger.info(f"Imported graph with {len(self.entities)} entities and {len(self.relations)} relations")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import graph: {e}")
            return False

class ClueMeisterGraphBuilder:
    """ClueMeister graph builder"""
    
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph
        self.entity_counter = 0
        self.relation_counter = 0
    
    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID"""
        self.entity_counter += 1
        return f"{prefix}_{self.entity_counter}_{int(datetime.utcnow().timestamp())}"
    
    def _generate_relation_id(self, prefix: str) -> str:
        """Generate unique relation ID"""
        self.relation_counter += 1
        return f"{prefix}_rel_{self.relation_counter}_{int(datetime.utcnow().timestamp())}"
    
    def add_missing_person(self, person_data: Dict[str, Any]) -> str:
        """Add missing person entity"""
        entity_id = self._generate_id("person")
        
        entity = Entity(
            id=entity_id,
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
                "description": person_data.get("description", "")
            },
            confidence=person_data.get("confidence", 1.0),
            source=person_data.get("source", "unknown")
        )
        
        return self.kg.add_entity(entity)
    
    def add_location(self, location_data: Dict[str, Any]) -> str:
        """Add location entity"""
        entity_id = self._generate_id("location")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.LOCATION,
            name=location_data.get("name", "Unknown Location"),
            properties={
                "coordinates": location_data.get("coordinates"),
                "address": location_data.get("address"),
                "terrain_type": location_data.get("terrain_type"),
                "accessibility": location_data.get("accessibility"),
                "landmarks": location_data.get("landmarks", []),
                "description": location_data.get("description", "")
            },
            confidence=location_data.get("confidence", 1.0),
            source=location_data.get("source", "unknown")
        )
        
        return self.kg.add_entity(entity)
    
    def add_clue(self, clue_data: Dict[str, Any]) -> str:
        """Add clue entity"""
        entity_id = self._generate_id("clue")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.CLUE,
            name=clue_data.get("name", "Unknown Clue"),
            properties={
                "type": clue_data.get("type"),
                "description": clue_data.get("description", ""),
                "found_location": clue_data.get("found_location"),
                "found_time": clue_data.get("found_time"),
                "reliability": clue_data.get("reliability", "unknown"),
                "source": clue_data.get("source", "unknown"),
                "details": clue_data.get("details", {})
            },
            confidence=clue_data.get("confidence", 1.0),
            source=clue_data.get("source", "unknown")
        )
        
        return self.kg.add_entity(entity)
    
    def add_witness_report(self, witness_data: Dict[str, Any]) -> str:
        """Add witness report entity"""
        entity_id = self._generate_id("witness")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.PERSON,
            name=witness_data.get("name", "Unknown Witness"),
            properties={
                "report": witness_data.get("report", ""),
                "confidence_level": witness_data.get("confidence_level", "unknown"),
                "location": witness_data.get("location"),
                "time": witness_data.get("time"),
                "details": witness_data.get("details", {})
            },
            confidence=witness_data.get("confidence", 1.0),
            source=witness_data.get("source", "unknown")
        )
        
        return self.kg.add_entity(entity)
    
    def add_photo_analysis(self, photo_data: Dict[str, Any]) -> str:
        """Add photo analysis entity"""
        entity_id = self._generate_id("photo")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.CLUE,
            name=f"Photo Analysis: {photo_data.get('filename', 'unknown')}",
            properties={
                "filename": photo_data.get("filename"),
                "detections": photo_data.get("detections", []),
                "person_analysis": photo_data.get("person_analysis", {}),
                "sar_context": photo_data.get("sar_context", {}),
                "location": photo_data.get("location"),
                "timestamp": photo_data.get("timestamp"),
                "analysis_confidence": photo_data.get("analysis_confidence", 0.5)
            },
            confidence=photo_data.get("confidence", 1.0),
            source=photo_data.get("source", "photo_analysis")
        )
        
        return self.kg.add_entity(entity)
    
    def add_historical_case(self, case_data: Dict[str, Any]) -> str:
        """Add historical case entity"""
        entity_id = self._generate_id("case")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.EVENT,
            name=f"Historical Case: {case_data.get('case_id', 'unknown')}",
            properties={
                "case_id": case_data.get("case_id"),
                "outcome": case_data.get("outcome"),
                "similarity_score": case_data.get("similarity_score"),
                "key_factors": case_data.get("key_factors", []),
                "lessons_learned": case_data.get("lessons_learned", []),
                "recommendations": case_data.get("recommendations", [])
            },
            confidence=case_data.get("confidence", 1.0),
            source=case_data.get("source", "history_agent")
        )
        
        return self.kg.add_entity(entity)
    
    def add_weather_condition(self, weather_data: Dict[str, Any]) -> str:
        """Add weather condition entity"""
        entity_id = self._generate_id("weather")
        
        entity = Entity(
            id=entity_id,
            type=EntityType.WEATHER,
            name=f"Weather: {weather_data.get('condition', 'unknown')}",
            properties={
                "condition": weather_data.get("condition"),
                "temperature": weather_data.get("temperature"),
                "wind_speed": weather_data.get("wind_speed"),
                "visibility": weather_data.get("visibility"),
                "forecast": weather_data.get("forecast", {}),
                "impact_on_search": weather_data.get("impact_on_search", "unknown")
            },
            confidence=weather_data.get("confidence", 1.0),
            source=weather_data.get("source", "weather_agent")
        )
        
        return self.kg.add_entity(entity)
    
    def link_entities(self, source_id: str, target_id: str, 
                     relation_type: RelationType, 
                     properties: Dict[str, Any] = None,
                     confidence: float = 1.0,
                     source: str = "unknown") -> str:
        """Link two entities"""
        relation_id = self._generate_relation_id("link")
        
        relation = Relation(
            id=relation_id,
            source_entity=source_id,
            target_entity=target_id,
            type=relation_type,
            properties=properties or {},
            confidence=confidence,
            source=source
        )
        
        return self.kg.add_relation(relation)
    
    def build_relationships_from_data(self, entities: List[str], data: Dict[str, Any]):
        """Automatically build relationships from data"""
        # Automatically build relationships based on data type
        if "photo_analysis" in data:
            photo_id = None
            for entity_id in entities:
                entity = self.kg.entities.get(entity_id)
                if entity and entity.type == EntityType.CLUE and "Photo Analysis" in entity.name:
                    photo_id = entity_id
                    break
            
            if photo_id:
                detections = data["photo_analysis"].get("detections", [])
                for detection in detections:
                    if detection.get("class") == "person":
                        person_id = self._generate_id("detected_person")
                        person_entity = Entity(
                            id=person_id,
                            type=EntityType.PERSON,
                            name="Detected Person",
                            properties={
                                "detection_confidence": detection.get("confidence"),
                                "bbox": detection.get("bbox"),
                                "hair_color": detection.get("hair_color"),
                                "clothing_color": detection.get("clothing_color"),
                                "gender": detection.get("gender")
                            },
                            confidence=detection.get("confidence", 0.5),
                            source="photo_analysis"
                        )
                        self.kg.add_entity(person_entity)
                        
                        self.link_entities(
                            photo_id, person_id, 
                            RelationType.FOUND_IN,
                            {"detection_method": "yolo", "confidence": detection.get("confidence", 0.5)},
                            confidence=detection.get("confidence", 0.5),
                            source="photo_analysis"
                        )
        
        if "interview_data" in data:
            for entity_id in entities:
                entity = self.kg.entities.get(entity_id)
                if entity and "witness" in entity.id:
                    for other_id in entities:
                        other_entity = self.kg.entities.get(other_id)
                        if other_entity and other_entity.type == EntityType.LOCATION:
                            self.link_entities(
                                entity_id, other_id,
                                RelationType.SEEN_AT,
                                {"report_type": "witness"},
                                confidence=0.8,
                                source="interview_analysis"
                            )


