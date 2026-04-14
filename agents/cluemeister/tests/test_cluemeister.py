#!/usr/bin/env python3
"""
ClueMeister Agent Test Script
Test knowledge graph construction, data fusion, and analysis functionality
Requires Neo4j running (use docker-compose up neo4j)
"""

import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder,
    EntityType, RelationType, Entity
)
from main import ClueMeisterAgent

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_knowledge_graph_basic():
    """Test basic knowledge graph functionality"""
    print("=== Testing Basic Knowledge Graph Functionality ===")
    
    # Create knowledge graph with Neo4j connection
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    print(f"Connecting to Neo4j at {neo4j_uri}...")
    try:
        kg = KnowledgeGraph(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password
        )
        builder = ClueMeisterGraphBuilder(kg)
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j: {e}")
        print("💡 Make sure Neo4j is running: docker-compose up neo4j")
        return None
    
    # Add missing person
    person_data = {
        "name": "John Doe",
        "age": 65,
        "gender": "male",
        "hair_color": "gray",
        "clothing": ["blue jacket", "jeans"],
        "last_known_location": "Central Park",
        "last_seen_time": "2025-01-05T14:30:00Z",
        "confidence": 0.9,
        "source": "emergency_call"
    }
    
    person_id = builder.add_missing_person(person_data)
    print(f"Added missing person: {person_id}")
    
    # Add location
    location_data = {
        "name": "Central Park Lake",
        "coordinates": {"lat": 40.7829, "lon": -73.9654},
        "terrain_type": "water_body",
        "accessibility": "moderate",
        "confidence": 0.8,
        "source": "gps_data"
    }
    
    location_id = builder.add_location(location_data)
    print(f"Added location: {location_id}")
    
    # Add clue
    clue_data = {
        "name": "Blue Jacket Found",
        "type": "clothing",
        "description": "Blue jacket found near the lake shore",
        "found_location": "Central Park Lake",
        "found_time": "2025-01-05T15:45:00Z",
        "reliability": "high",
        "confidence": 0.85,
        "source": "field_search"
    }
    
    clue_id = builder.add_clue(clue_data)
    print(f"Added clue: {clue_id}")
    
    # Add relation
    relation_id = builder.link_entities(
        person_id, location_id,
        RelationType.LAST_SEEN,
        {"time": "2025-01-05T14:30:00Z", "witness": "park_visitor"},
        confidence=0.8,
        source="witness_report"
    )
    print(f"Added relation: {relation_id}")
    
    # Link clue to person
    clue_relation_id = builder.link_entities(
        clue_id, person_id,
        RelationType.OWNS,
        {"item_type": "clothing", "match_confidence": 0.9},
        confidence=0.85,
        source="evidence_analysis"
    )
    print(f"Linked clue to person: {clue_relation_id}")
    
    # Generate insights
    insights = kg.generate_insights()
    print(f"Graph insights: {json.dumps(insights, indent=2, ensure_ascii=False)}")
    
    # Find paths
    paths = kg.find_paths(person_id, location_id)
    print(f"Paths from person to location: {paths}")
    
    # Close connection
    kg.close()
    
    return kg

def test_photo_analysis_processing():
    """Test photo analysis data processing"""
    print("\n=== Test photo analysis data processing ===")
    
    cluemeister = ClueMeisterAgent()
    
    photo_data = {
        "filename": "search_area_001.jpg",
        "detections": [
            {
                "class": "person",
                "confidence": 0.85,
                "bbox": [100, 200, 300, 400],
                "hair_color": "gray",
                "clothing_color": "blue",
                "gender": "male",
                "person_id": 1
            },
            {
                "class": "boat",
                "confidence": 0.92,
                "bbox": [500, 300, 700, 500]
            }
        ],
        "person_analysis": {
            "total_people": 1,
            "faces_detected": 1,
            "face_encodings": []
        },
        "sar_context": {
            "search_priority": "HIGH",
            "urgency_level": "MEDIUM",
            "accessibility": {
                "score": 70,
                "level": "MODERATE"
            },
            "emergency_equipment": [],
            "weather_conditions": {
                "visibility": "GOOD",
                "lighting": "DAY"
            }
        },
        "confidence": 0.8,
        "source": "photo_analysis"
    }
    
    entity_ids = cluemeister.process_photo_analysis(photo_data)
    print(f"Entities created: {len(entity_ids)}")
    print(f"Entity IDs: {entity_ids}")
    
    insights = cluemeister.knowledge_graph.generate_insights()
    print(f"Graph stats: entities={insights['total_entities']}, relations={insights['total_relations']}")
    
    return cluemeister

def test_interview_analysis_processing():
    """Test interview analysis data processing"""
    print("\n=== Test interview analysis data processing ===")
    
    cluemeister = ClueMeisterAgent()
    
    interview_data = {
        "analysis": {
            "important_sections": [
                {
                    "section": "I saw an elderly man in a blue jacket walking near the lake around 2:30 PM",
                    "importance_score": 9,
                    "reason": "Direct witness observation with specific details"
                },
                {
                    "section": "He seemed confused and was looking around as if lost",
                    "importance_score": 8,
                    "reason": "Behavioral indicators of disorientation"
                }
            ],
            "entity_extraction": [
                {
                    "section": "I saw an elderly man in a blue jacket walking near the lake around 2:30 PM",
                    "entities": {
                        "people": ["elderly man"],
                        "places": ["lake", "Central Park"],
                        "times": ["2:30 PM"]
                    }
                }
            ],
            "high_confidence_sections": [
                {
                    "section": "I saw an elderly man in a blue jacket walking near the lake around 2:30 PM",
                    "confidence_score": 9,
                    "confidence_level": "high"
                }
            ]
        },
        "confidence": 0.9,
        "source": "interview_analysis"
    }
    
    entity_ids = cluemeister.process_interview_analysis(interview_data)
    print(f"Entities created: {len(entity_ids)}")
    print(f"Entity IDs: {entity_ids}")
   
    insights = cluemeister.knowledge_graph.generate_insights()
    print(f"Graph stats: entities={insights['total_entities']}, relations={insights['total_relations']}")
    
    return cluemeister

def test_cross_agent_correlations():
    """Test cross-agent correlation analysis"""
    print("\n=== Test cross-agent correlation analysis ===")
    
    cluemeister = ClueMeisterAgent()
    
    photo_data = {
        "filename": "search_area_001.jpg",
        "detections": [
            {
                "class": "person",
                "confidence": 0.85,
                "bbox": [100, 200, 300, 400],
                "hair_color": "gray",
                "clothing_color": "blue",
                "gender": "male"
            }
        ],
        "person_analysis": {"total_people": 1},
        "sar_context": {"search_priority": "HIGH"},
        "source": "photo_analysis"
    }
    
    interview_data = {
        "analysis": {
            "important_sections": [
                {
                    "section": "I saw an elderly man in a blue jacket near the lake",
                    "importance_score": 9
                }
            ],
            "entity_extraction": [
                {
                    "entities": {
                        "people": ["elderly man"],
                        "places": ["lake"]
                    }
                }
            ]
        },
        "source": "interview_analysis"
    }
    
    cluemeister.process_photo_analysis(photo_data)
    cluemeister.process_interview_analysis(interview_data)
    
    correlations = cluemeister.analyze_cross_agent_correlations()
    print(f"Correlation analysis results: {json.dumps(correlations, indent=2, ensure_ascii=False)}")
    
    return cluemeister

def test_search_recommendations():
    """Test search recommendation generation"""
    print("\n=== Test search recommendation generation ===")
    
    cluemeister = ClueMeisterAgent()
    
    photo_data = {
        "filename": "search_area_001.jpg",
        "detections": [{"class": "person", "confidence": 0.85}],
        "person_analysis": {"total_people": 1},
        "sar_context": {"search_priority": "CRITICAL", "urgency_level": "HIGH"},
        "source": "photo_analysis"
    }
    
    interview_data = {
        "analysis": {
            "important_sections": [
                {
                    "section": "I saw the missing person near the lake",
                    "importance_score": 10
                }
            ]
        },
        "source": "interview_analysis"
    }
    
    cluemeister.process_photo_analysis(photo_data)
    cluemeister.process_interview_analysis(interview_data)
    
    recommendations = cluemeister.generate_search_recommendations()
    print(f"Search recommendations: {json.dumps(recommendations, indent=2, ensure_ascii=False)}")
    
    return cluemeister

def test_knowledge_graph_export_import():
    """Test knowledge graph export and import"""
    print("\n=== Test knowledge graph export and import ===")
    
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    kg1 = KnowledgeGraph(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password
    )
    builder = ClueMeisterGraphBuilder(kg1)
    
    person_id = builder.add_missing_person({
        "name": "Test Person",
        "age": 30,
        "confidence": 0.9
    })
    
    location_id = builder.add_location({
        "name": "Test Location",
        "confidence": 0.8
    })
    
    builder.link_entities(person_id, location_id, RelationType.SEEN_AT)

    export_data = kg1.export_graph()
    print(f"Export data: entities={len(export_data['entities'])}, relations={len(export_data['relations'])}")
    
    # Note: Import to same Neo4j instance will add duplicate data
    # In production, you'd want to use a different database or clear first
    print("Note: Import would add to existing Neo4j database")
    
    insights1 = kg1.generate_insights()
    
    print(f"Graph stats: entities={insights1['total_entities']}, relations={insights1['total_relations']}")
    print(f"View in Neo4j Browser: http://localhost:7474")
    print(f"Run: MATCH (n) RETURN n LIMIT 25")
    
    return kg1

def run_all_tests():
    print("Start ClueMeister Agent testing")
    print("=" * 50)
    
    try:

        test_knowledge_graph_basic()
        
        test_photo_analysis_processing()
        test_interview_analysis_processing()
        

        test_cross_agent_correlations()
        

        test_search_recommendations()
        

        test_knowledge_graph_export_import()
        
        print("\nAll tests completed!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()


