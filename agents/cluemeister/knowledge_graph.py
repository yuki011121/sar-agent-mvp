#!/usr/bin/env python3
"""
Knowledge Graph for ClueMeister Agent
Build and manage knowledge graphs for search and rescue missions
Uses Neo4j as the primary graph database
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, Counter

# Try to import Neo4j - optional dependency
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Neo4j driver not available. Install with: pip install neo4j")

# Try to import visualization libraries - optional
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.offline import plot
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

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
    """Search and rescue knowledge graph using Neo4j"""
    
    def __init__(self, neo4j_uri: str = None, 
                 neo4j_user: str = None, neo4j_password: str = None):
        """
        Initialize knowledge graph with Neo4j
        
        Args:
            neo4j_uri: Neo4j connection URI (e.g., 'bolt://localhost:7687')
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
        """
        if not NEO4J_AVAILABLE:
            raise ImportError("Neo4j driver not available. Install with: pip install neo4j")
        
        # Neo4j connection
        uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = neo4j_user or os.getenv("NEO4J_USER", "neo4j")
        password = neo4j_password or os.getenv("NEO4J_PASSWORD", "password")
        
        try:
            self.neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
            logger.info(f"Connected to Neo4j at {uri}")
            
            # Verify connection
            with self.neo4j_driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise ConnectionError(f"Failed to connect to Neo4j at {uri}: {e}")
        
        self.entity_counter = 0
        self.relation_counter = 0
        
    def add_entity(self, entity: Entity) -> str:
        """Add entity to Neo4j graph"""
        return self._add_entity_to_neo4j(entity)
    
    def _add_entity_to_neo4j(self, entity: Entity) -> str:
        """Add entity to Neo4j database"""
        
        try:
            with self.neo4j_driver.session() as session:
                # Convert properties to Neo4j-friendly format
                props = {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type.value,
                    "confidence": entity.confidence,
                    "source": entity.source,
                    "timestamp": entity.timestamp,
                    **{k: json.dumps(v) if isinstance(v, (dict, list)) else v 
                       for k, v in entity.properties.items()}
                }
                
                # Use MERGE to handle upserts
                # Sanitize type name for Neo4j label (must be valid identifier)
                type_label = entity.type.value.capitalize().replace(" ", "_")
                query = f"""
                MERGE (n:Entity {{id: $id}})
                SET n += $props
                SET n:EntityType:{type_label}
                RETURN n
                """
                result = session.run(query, id=entity.id, props=props)
                result.consume()  # Consume result to ensure query executes
                logger.debug(f"Added entity to Neo4j: {entity.id} ({entity.type.value})")
                return entity.id
        except Exception as e:
            logger.error(f"Failed to add entity to Neo4j: {e}")
            raise
    
    def add_relation(self, relation: Relation) -> str:
        """Add relation to Neo4j graph"""
        return self._add_relation_to_neo4j(relation)
    
    def _add_relation_to_neo4j(self, relation: Relation) -> str:
        """Add relation to Neo4j database"""
        
        try:
            with self.neo4j_driver.session() as session:
                # Convert relation type to Neo4j-friendly format (uppercase, no spaces)
                rel_type = relation.type.value.upper().replace('_', '_')
                
                props = {
                    "id": relation.id,
                    "confidence": relation.confidence,
                    "source": relation.source,
                    "timestamp": relation.timestamp,
                    **{k: json.dumps(v) if isinstance(v, (dict, list)) else v 
                       for k, v in relation.properties.items()}
                }
                
                # Create relationship between entities
                query = f"""
                MATCH (a:Entity {{id: $source_id}})
                MATCH (b:Entity {{id: $target_id}})
                MERGE (a)-[r:{rel_type} {{id: $rel_id}}]->(b)
                SET r += $props
                RETURN r
                """
                result = session.run(query, 
                           source_id=relation.source_entity,
                           target_id=relation.target_entity,
                           rel_id=relation.id,
                           props=props)
                result.consume()  # Consume result to ensure query executes
                logger.debug(f"Added relation to Neo4j: {relation.id} ({relation.type.value})")
                return relation.id
        except Exception as e:
            logger.error(f"Failed to add relation to Neo4j: {e}")
            raise
    
    def find_entities(self, entity_type: EntityType = None, 
                     properties: Dict[str, Any] = None) -> List[Entity]:
        """Find entities using Cypher query"""
        results = []
        
        try:
            with self.neo4j_driver.session() as session:
                # Build Cypher query
                if entity_type:
                    type_label = entity_type.value.capitalize().replace(" ", "_")
                    query = f"MATCH (n:Entity:{type_label})"
                else:
                    query = "MATCH (n:Entity)"
                
                # Add property filters
                where_clauses = []
                if properties:
                    for key, value in properties.items():
                        if isinstance(value, str):
                            where_clauses.append(f"n.{key} = '{value}'")
                        else:
                            where_clauses.append(f"n.{key} = {json.dumps(value)}")
                
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
                
                query += " RETURN n"
                
                # Execute query
                result = session.run(query)
                
                for record in result:
                    node = record["n"]
                    props = dict(node)
                    
                    # Reconstruct Entity object
                    entity = Entity(
                        id=props.pop("id"),
                        type=EntityType(props.pop("type")),
                        name=props.pop("name", "Unknown"),
                        properties=props,
                        confidence=props.pop("confidence", 1.0),
                        source=props.pop("source", "unknown"),
                        timestamp=props.pop("timestamp")
                    )
                    results.append(entity)
        
        except Exception as e:
            logger.error(f"Failed to find entities: {e}")
        
        return results
    
    def find_relations(self, relation_type: RelationType = None,
                      source_entity: str = None,
                      target_entity: str = None) -> List[Relation]:
        """Find relations using Cypher query"""
        results = []
        
        try:
            with self.neo4j_driver.session() as session:
                # Build Cypher query
                if relation_type:
                    rel_type = relation_type.value.upper().replace('_', '_')
                    query = f"MATCH (a:Entity)-[r:{rel_type}]->(b:Entity)"
                else:
                    query = "MATCH (a:Entity)-[r]->(b:Entity)"
                
                where_clauses = []
                if source_entity:
                    where_clauses.append(f"a.id = '{source_entity}'")
                if target_entity:
                    where_clauses.append(f"b.id = '{target_entity}'")
                
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
                
                query += " RETURN a, r, b"
                
                # Execute query
                result = session.run(query)
                
                for record in result:
                    rel = record["r"]
                    rel_type_str = type(rel).__name__ if hasattr(rel, '__class__') else str(rel)
                    # Try to get relation type from record
                    try:
                        rel_type_name = rel_type_str.lower().replace('_', '_')
                        # Map common Neo4j relation types to our RelationType enum
                        rel_type_map = {
                            'seen_at': RelationType.SEEN_AT,
                            'last_seen': RelationType.LAST_SEEN,
                            'traveled_to': RelationType.TRAVELED_TO,
                            'owns': RelationType.OWNS,
                            'wears': RelationType.WEARS,
                            'near': RelationType.NEAR,
                            'found_in': RelationType.FOUND_IN,
                            'requires': RelationType.REQUIRES,
                            'affected_by': RelationType.AFFECTED_BY,
                            'located_in': RelationType.LOCATED_IN,
                        }
                        rel_type = rel_type_map.get(rel_type_name, relation_type if relation_type else RelationType.CONNECTED_TO)
                    except:
                        rel_type = relation_type if relation_type else RelationType.CONNECTED_TO
                    
                    props = dict(rel)
                    
                    # Reconstruct Relation object
                    relation = Relation(
                        id=props.pop("id", f"rel_{len(results)}"),
                        source_entity=dict(record["a"])["id"],
                        target_entity=dict(record["b"])["id"],
                        type=rel_type,
                        properties=props,
                        confidence=props.pop("confidence", 1.0),
                        source=props.pop("source", "unknown"),
                        timestamp=props.pop("timestamp")
                    )
                    results.append(relation)
        
        except Exception as e:
            logger.error(f"Failed to find relations: {e}")
        
        return results
    
    def get_entity_neighbors(self, entity_id: str, 
                           relation_types: List[RelationType] = None) -> List[Tuple[Entity, Relation]]:
        """Get entity neighbors and relations using Cypher query"""
        neighbors = []
        
        try:
            with self.neo4j_driver.session() as session:
                # Build relation type filter
                if relation_types:
                    rel_filters = "|".join([rt.value.upper().replace('_', '_') for rt in relation_types])
                    query = f"""
                    MATCH (a:Entity {{id: $entity_id}})-[r:{rel_filters}]-(b:Entity)
                    RETURN b, r, type(r) as rel_type
                    """
                else:
                    query = """
                    MATCH (a:Entity {id: $entity_id})-[r]-(b:Entity)
                    RETURN b, r, type(r) as rel_type
                    """
                
                result = session.run(query, entity_id=entity_id)
                
                for record in result:
                    node = record["b"]
                    rel = record["r"]
                    rel_type_str = record["rel_type"]
                    
                    # Reconstruct Entity
                    node_props = dict(node)
                    entity = Entity(
                        id=node_props.pop("id"),
                        type=EntityType(node_props.pop("type")),
                        name=node_props.pop("name", "Unknown"),
                        properties=node_props,
                        confidence=node_props.pop("confidence", 1.0),
                        source=node_props.pop("source", "unknown"),
                        timestamp=node_props.pop("timestamp")
                    )
                    
                    # Reconstruct Relation
                    rel_props = dict(rel)
                    # Map relation type string to enum
                    rel_type_name = rel_type_str.lower().replace('_', '_')
                    rel_type_map = {
                        'seen_at': RelationType.SEEN_AT,
                        'last_seen': RelationType.LAST_SEEN,
                        'traveled_to': RelationType.TRAVELED_TO,
                        'owns': RelationType.OWNS,
                        'wears': RelationType.WEARS,
                        'near': RelationType.NEAR,
                        'found_in': RelationType.FOUND_IN,
                        'requires': RelationType.REQUIRES,
                        'affected_by': RelationType.AFFECTED_BY,
                        'located_in': RelationType.LOCATED_IN,
                    }
                    mapped_rel_type = rel_type_map.get(rel_type_name, RelationType.CONNECTED_TO)
                    
                    relation = Relation(
                        id=rel_props.pop("id", f"rel_{len(neighbors)}"),
                        source_entity=entity_id,
                        target_entity=entity.id,
                        type=mapped_rel_type,
                        properties=rel_props,
                        confidence=rel_props.pop("confidence", 1.0),
                        source=rel_props.pop("source", "unknown"),
                        timestamp=rel_props.pop("timestamp")
                    )
                    
                    neighbors.append((entity, relation))
        
        except Exception as e:
            logger.error(f"Failed to get entity neighbors: {e}")
        
        return neighbors
    
    def find_paths(self, source_entity: str, target_entity: str, 
                  max_length: int = 3) -> List[List[str]]:
        """Find paths between two entities using Cypher"""
        paths = []
        
        try:
            with self.neo4j_driver.session() as session:
                query = """
                MATCH path = (start:Entity {id: $source_id})-[*1..%d]-(end:Entity {id: $target_id})
                RETURN [n in nodes(path) | n.id] as path_nodes
                LIMIT 100
                """ % max_length
                
                result = session.run(query, source_id=source_entity, target_id=target_entity)
                
                for record in result:
                    path_nodes = record["path_nodes"]
                    if path_nodes:
                        paths.append(path_nodes)
        
        except Exception as e:
            logger.error(f"Failed to find paths: {e}")
        
        return paths
    
    def calculate_entity_importance(self, entity_id: str) -> float:
        """Calculate entity importance score using Neo4j"""
        try:
            with self.neo4j_driver.session() as session:
                # Get entity
                query = "MATCH (n:Entity {id: $entity_id}) RETURN n"
                result = session.run(query, entity_id=entity_id)
                record = result.single()
                
                if not record:
                    return 0.0
                
                node = record["n"]
                props = dict(node)
                entity_type = EntityType(props.get("type", "unknown"))
                confidence = props.get("confidence", 1.0)
                
                # Get degree (number of connections)
                degree_query = """
                MATCH (n:Entity {id: $entity_id})-[r]-(connected)
                RETURN count(r) as degree
                """
                degree_result = session.run(degree_query, entity_id=entity_id)
                degree_record = degree_result.single()
                degree = degree_record["degree"] if degree_record else 0
                
                # Base score
                importance = confidence
                
                # Degree score
                importance += degree * 0.1
                
                # Note: Betweenness centrality is expensive to calculate in Neo4j
                # For now, we skip it. Can be added later if needed using Neo4j GDS library
                
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
                
                importance *= type_weights.get(entity_type, 1.0)
                
                return importance
        
        except Exception as e:
            logger.error(f"Failed to calculate entity importance: {e}")
            return 0.0
    
    def find_clusters(self) -> List[List[str]]:
        """Find entity clusters using Neo4j (weakly connected components)"""
        clusters = []
        
        try:
            with self.neo4j_driver.session() as session:
                # Find weakly connected components
                # This is a simplified version - Neo4j GDS library has better algorithms
                query = """
                MATCH (n:Entity)
                WITH collect(DISTINCT id(n)) as node_ids
                UNWIND node_ids as node_id
                MATCH path = shortestPath((a)-[*]-(b))
                WHERE id(a) = node_id
                RETURN collect(DISTINCT a.id) as component
                LIMIT 100
                """
                
                # Simpler approach: get all connected components
                # This is a basic implementation
                query = """
                MATCH (n:Entity)
                OPTIONAL MATCH (n)-[*1..10]-(connected:Entity)
                WITH n, collect(DISTINCT connected.id) as connected_ids
                WHERE size(connected_ids) > 0
                RETURN collect(DISTINCT n.id) + connected_ids as cluster
                """
                
                result = session.run(query)
                
                for record in result:
                    cluster = record["cluster"]
                    if cluster:
                        clusters.append(list(set(cluster)))  # Remove duplicates
        
        except Exception as e:
            logger.error(f"Failed to find clusters: {e}")
            # Return at least empty clusters for each entity as fallback
            try:
                simple_query = "MATCH (n:Entity) RETURN collect(n.id) as all_ids"
                simple_result = session.run(simple_query)
                record = simple_result.single()
                if record:
                    all_ids = record["all_ids"]
                    # Return each entity as its own cluster (simple fallback)
                    clusters = [[eid] for eid in all_ids]
            except:
                pass
        
        return clusters
    
    def extract_timeline(self) -> List[Dict[str, Any]]:
        """Extract timeline from Neo4j"""
        timeline = []
        
        try:
            with self.neo4j_driver.session() as session:
                query = """
                MATCH (n:Entity:Time)
                RETURN n.id as id, n.timestamp as timestamp, 
                       coalesce(n.description, n.name) as description, 
                       n.confidence as confidence
                ORDER BY n.timestamp
                """
                
                result = session.run(query)
                
                for record in result:
                    timeline.append({
                        "entity_id": record["id"],
                        "timestamp": record["timestamp"],
                        "description": record["description"],
                        "confidence": record["confidence"]
                    })
        
        except Exception as e:
            logger.error(f"Failed to extract timeline: {e}")
        
        return timeline
    
    def generate_insights(self) -> Dict[str, Any]:
        """Generate insights from Neo4j"""
        insights = {
            "total_entities": 0,
            "total_relations": 0,
            "entity_types": {},
            "relation_types": {},
            "clusters": len(self.find_clusters()),
            "timeline_events": len(self.extract_timeline()),
            "most_important_entities": []
        }
        
        try:
            with self.neo4j_driver.session() as session:
                # Count entities
                count_query = "MATCH (n:Entity) RETURN count(n) as count"
                result = session.run(count_query)
                insights["total_entities"] = result.single()["count"]
                
                # Count relations
                rel_count_query = "MATCH ()-[r]->() RETURN count(r) as count"
                rel_result = session.run(rel_count_query)
                insights["total_relations"] = rel_result.single()["count"]
                
                # Entity types
                type_query = """
                MATCH (n:Entity)
                RETURN n.type as type, count(n) as count
                """
                type_result = session.run(type_query)
                insights["entity_types"] = {record["type"]: record["count"] for record in type_result}
                
                # Relation types
                rel_type_query = """
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as count
                """
                rel_type_result = session.run(rel_type_query)
                insights["relation_types"] = {record["rel_type"]: record["count"] for record in rel_type_result}
                
                # Find most important entities
                entities_query = "MATCH (n:Entity) RETURN n.id as id LIMIT 100"
                entities_result = session.run(entities_query)
                
                entity_importance = {}
                for record in entities_result:
                    entity_id = record["id"]
                    entity_importance[entity_id] = self.calculate_entity_importance(entity_id)
                
                top_entities = sorted(entity_importance.items(), key=lambda x: x[1], reverse=True)[:5]
                
                for entity_id, importance in top_entities:
                    entity_result = session.run("MATCH (n:Entity {id: $id}) RETURN n", id=entity_id)
                    entity_record = entity_result.single()
                    if entity_record:
                        node = entity_record["n"]
                        props = dict(node)
                        insights["most_important_entities"].append({
                            "id": entity_id,
                            "name": props.get("name", "Unknown"),
                            "type": props.get("type", "unknown"),
                            "importance": importance,
                            "confidence": props.get("confidence", 1.0)
                        })
        
        except Exception as e:
            logger.error(f"Failed to generate insights: {e}")
        
        return insights
    
    def export_graph(self) -> Dict[str, Any]:
        """Export graph data from Neo4j"""
        entities_dict = {}
        relations_dict = {}
        
        try:
            with self.neo4j_driver.session() as session:
                # Export all entities
                entities_query = "MATCH (n:Entity) RETURN n"
                entities_result = session.run(entities_query)
                for record in entities_result:
                    node = record["n"]
                    props = dict(node)
                    entity_id = props.pop("id")
                    entities_dict[entity_id] = {
                        "id": entity_id,
                        "type": props.pop("type"),
                        "name": props.pop("name", "Unknown"),
                        "properties": props,
                        "confidence": props.pop("confidence", 1.0),
                        "source": props.pop("source", "unknown"),
                        "timestamp": props.pop("timestamp")
                    }
                
                # Export all relations
                relations_query = "MATCH (a:Entity)-[r]->(b:Entity) RETURN a, r, b"
                relations_result = session.run(relations_query)
                for record in relations_result:
                    rel = record["r"]
                    props = dict(rel)
                    rel_id = props.pop("id")
                    relations_dict[rel_id] = {
                        "id": rel_id,
                        "source_entity": dict(record["a"])["id"],
                        "target_entity": dict(record["b"])["id"],
                        "type": type(rel).__name__ if hasattr(rel, '__class__') else props.pop("type", "UNKNOWN"),
                        "properties": props,
                        "confidence": props.pop("confidence", 1.0),
                        "source": props.pop("source", "unknown"),
                        "timestamp": props.pop("timestamp")
                    }
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
        
        return {
            "entities": entities_dict,
            "relations": relations_dict,
            "insights": self.generate_insights(),
            "export_timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def export_visualization_data(self, output_format: str = "json") -> Dict[str, Any]:
        """
        Export graph data in format suitable for visualization
        
        Args:
            output_format: 'json' for JSON format, 'plotly' for Plotly format
        
        Returns:
            Dictionary with nodes and edges for visualization
        """
        nodes = []
        edges = []
        
        # Color mapping for entity types
        type_colors = {
            EntityType.PERSON: "#FF6B6B",
            EntityType.LOCATION: "#4ECDC4",
            EntityType.CLUE: "#FFE66D",
            EntityType.EVENT: "#95E1D3",
            EntityType.AREA: "#F38181",
            EntityType.RESOURCE: "#AA96DA",
            EntityType.WEATHER: "#95E1D3",
            EntityType.TIME: "#C7CEEA",
            EntityType.OBJECT: "#FFB6C1",
            EntityType.TERRAIN: "#87CEEB"
        }
        
        # Build nodes and edges from Neo4j
        try:
            with self.neo4j_driver.session() as session:
                # Get all entities
                entities_query = "MATCH (n:Entity) RETURN n LIMIT 1000"
                entities_result = session.run(entities_query)
                for record in entities_result:
                    node = record["n"]
                    props = dict(node)
                    entity_id = props.pop("id")
                    entity_type = EntityType(props.pop("type", "unknown"))
                    name = props.pop("name", "Unknown")
                    confidence = props.pop("confidence", 1.0)
                    
                    nodes.append({
                        "id": entity_id,
                        "label": name[:30] + "..." if len(name) > 30 else name,
                        "type": entity_type.value,
                        "size": max(10, min(50, confidence * 50 + 10)),
                        "color": type_colors.get(entity_type, "#CCCCCC"),
                        "confidence": confidence,
                        "properties": props,
                        "source": props.pop("source", "unknown")
                    })
                
                # Get all relations
                relations_query = "MATCH (a:Entity)-[r]->(b:Entity) RETURN a, r, b LIMIT 5000"
                relations_result = session.run(relations_query)
                for record in relations_result:
                    rel = record["r"]
                    rel_props = dict(rel)
                    rel_id = rel_props.pop("id", None) or f"rel_{len(edges)}"
                    rel_type_str = type(rel).__name__ if hasattr(rel, '__class__') else "RELATED_TO"
                    
                    edges.append({
                        "id": rel_id,
                        "source": dict(record["a"])["id"],
                        "target": dict(record["b"])["id"],
                        "label": rel_type_str.replace("_", " ").title(),
                        "type": rel_type_str.lower(),
                        "confidence": rel_props.pop("confidence", 1.0),
                        "width": max(1, min(5, rel_props.pop("confidence", 1.0) * 5)),
                        "properties": rel_props
                    })
        except Exception as e:
            logger.error(f"Failed to export visualization data: {e}")
        
        result = {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "export_timestamp": datetime.utcnow().isoformat() + "Z",
                "format": output_format
            }
        }
        
        # Add Plotly-specific format if requested
        if output_format == "plotly" and PLOTLY_AVAILABLE:
            result["plotly"] = self._create_plotly_visualization(nodes, edges)
        
        return result
    
    def _create_plotly_visualization(self, nodes: List[Dict], edges: List[Dict]) -> Dict[str, Any]:
        """Create Plotly network visualization data"""
        if not PLOTLY_AVAILABLE:
            return {}
        
        try:
            # Simple layout using node positions from a grid
            # Neo4j doesn't have built-in layout, so we use a simple circular or grid layout
            import math
            n_nodes = len(nodes)
            if n_nodes == 0:
                return {}
            
            # Circular layout
            radius = max(10, n_nodes * 0.5)
            angle_step = 2 * math.pi / n_nodes if n_nodes > 0 else 0
            pos = {}
            for i, node in enumerate(nodes):
                angle = i * angle_step
                pos[node["id"]] = (radius * math.cos(angle), radius * math.sin(angle))
            
            # Extract coordinates
            node_x = [pos[node["id"]][0] for node in nodes]
            node_y = [pos[node["id"]][1] for node in nodes]
            
            # Create edge traces
            edge_x = []
            edge_y = []
            for edge in edges:
                source_id = edge["source"]
                target_id = edge["target"]
                if source_id in pos and target_id in pos:
                    edge_x.extend([pos[source_id][0], pos[target_id][0], None])
                    edge_y.extend([pos[source_id][1], pos[target_id][1], None])
            
            # Create node trace
            node_trace = {
                "x": node_x,
                "y": node_y,
                "mode": "markers+text",
                "type": "scatter",
                "hoverinfo": "text",
                "text": [node["label"] for node in nodes],
                "textposition": "middle right",
                "marker": {
                    "size": [node["size"] for node in nodes],
                    "color": [node["color"] for node in nodes],
                    "line": {"width": 2, "color": "white"}
                }
            }
            
            # Create edge trace
            edge_trace = {
                "x": edge_x,
                "y": edge_y,
                "line": {"width": 1, "color": "#888"},
                "hoverinfo": "none",
                "mode": "lines",
                "type": "scatter"
            }
            
            return {
                "edge_trace": edge_trace,
                "node_trace": node_trace,
                "layout": {
                    "title": "ClueMeister Knowledge Graph",
                    "showlegend": False,
                    "hovermode": 'closest',
                    "margin": dict(b=20, l=5, r=5, t=40),
                    "annotations": [],
                    "xaxis": dict(showgrid=False, zeroline=False, showticklabels=False),
                    "yaxis": dict(showgrid=False, zeroline=False, showticklabels=False)
                }
            }
        except Exception as e:
            logger.error(f"Failed to create Plotly visualization: {e}")
            return {}
    
    def visualize_graph_html(self, output_path: str = "knowledge_graph.html") -> str:
        """
        Generate interactive HTML visualization of the graph
        
        Args:
            output_path: Path to save HTML file
        
        Returns:
            Path to saved HTML file
        """
        if not PLOTLY_AVAILABLE:
            logger.warning("Plotly not available. Cannot generate visualization.")
            return ""
        
        try:
            viz_data = self.export_visualization_data(output_format="plotly")
            if "plotly" not in viz_data or not viz_data["plotly"]:
                logger.warning("Could not generate plotly data")
                return ""
            
            plotly_data = viz_data["plotly"]
            # Convert dict traces to plotly objects
            edge_trace = go.Scatter(**plotly_data["edge_trace"])
            node_trace = go.Scatter(**plotly_data["node_trace"])
            layout = go.Layout(**plotly_data["layout"])
            
            fig = go.Figure(data=[edge_trace, node_trace], layout=layout)
            
            plot(fig, filename=output_path, auto_open=False)
            logger.info(f"Visualization saved to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to generate HTML visualization: {e}")
            return ""
    
    def get_neo4j_cypher_queries(self) -> List[str]:
        """Generate Cypher queries to reproduce graph in Neo4j (already in Neo4j, return empty)"""
        # Since we're already using Neo4j, we don't need to generate queries
        # This method is kept for compatibility
        return []
    
    def _get_all_entities_from_neo4j(self) -> List[Entity]:
        """Helper method to get all entities from Neo4j"""
        return self.find_entities()
    
    def close(self):
        """Close Neo4j connection if open"""
        if self.neo4j_driver:
            self.neo4j_driver.close()
            logger.info("Neo4j connection closed")
    
    def import_graph(self, data: Dict[str, Any]) -> bool:
        """Import graph data into Neo4j"""
        try:
            # Clear existing data (optional - comment out if you want to keep existing data)
            # with self.neo4j_driver.session() as session:
            #     session.run("MATCH (n) DETACH DELETE n")
            
            # Import entities
            entities_count = 0
            for eid, entity_data in data.get("entities", {}).items():
                entity = Entity(**entity_data)
                entity.type = EntityType(entity.type) if isinstance(entity.type, str) else entity.type
                self.add_entity(entity)
                entities_count += 1
            
            # Import relations
            relations_count = 0
            for rid, relation_data in data.get("relations", {}).items():
                relation = Relation(**relation_data)
                relation.type = RelationType(relation.type) if isinstance(relation.type, str) else relation.type
                self.add_relation(relation)
                relations_count += 1
            
            logger.info(f"Imported graph with {entities_count} entities and {relations_count} relations")
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


