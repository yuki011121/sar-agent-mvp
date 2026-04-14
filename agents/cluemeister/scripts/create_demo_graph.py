#!/usr/bin/env python3
"""
Create a demo knowledge graph for presentation
Shows cross-source correlations, historical patterns, and intelligent recommendations
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder,
    EntityType, RelationType, Entity
)

def create_demo_graph():
    """Create a comprehensive demo graph for presentation"""
    print("🎨 Creating Demo Knowledge Graph for Presentation")
    print("=" * 60)
    
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    try:
        kg = KnowledgeGraph(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password
        )
        builder = ClueMeisterGraphBuilder(kg)
        
        print("\n📝 Step 1: Creating Missing Person (Main Subject)")
        print("-" * 60)
        
        # Main missing person
        person_id = builder.add_missing_person({
            "name": "John Smith",
            "age": 72,
            "gender": "male",
            "hair_color": "gray",
            "clothing": ["blue jacket", "khaki pants"],
            "medical_conditions": ["dementia"],
            "last_known_location": "Central Park",
            "last_seen_time": "2025-01-10T14:30:00Z",
            "confidence": 0.95,
            "source": "emergency_call"
        })
        print(f"   ✅ Person: {person_id} (John Smith, 72, dementia)")
        
        print("\n📝 Step 2: Creating Photo Analysis Data")
        print("-" * 60)
        
        # Photo analysis: detected person matching description
        photo_person_id = builder.add_missing_person({
            "name": "Photo Detection",
            "hair_color": "gray",
            "clothing": ["blue jacket"],
            "age_range": "70-75",
            "confidence": 0.85,
            "source": "photo_analysis",
            "properties": {
                "detection_time": "2025-01-10T15:20:00Z",
                "location": "Central Park Lake"
            }
        })
        print(f"   ✅ Photo Person: {photo_person_id}")
        
        # Photo clue
        photo_clue_id = builder.add_clue({
            "name": "Blue Jacket Detected",
            "type": "clothing",
            "description": "Blue jacket matching description found in photo",
            "confidence": 0.88,
            "source": "photo_analysis",
            "properties": {
                "detection_method": "computer_vision",
                "location": "Central Park Lake area"
            }
        })
        print(f"   ✅ Photo Clue: {photo_clue_id}")
        
        # Link photo person to clue
        builder.link_entities(
            photo_person_id, photo_clue_id,
            RelationType.OWNS,
            {"match_confidence": 0.9},
            confidence=0.88,
            source="photo_analysis"
        )
        
        print("\n📝 Step 3: Creating Interview Analysis Data")
        print("-" * 60)
        
        # Interview witness report
        interview_person_id = builder.add_missing_person({
            "name": "Witness Report",
            "hair_color": "gray",
            "age_range": "elderly",
            "confidence": 0.82,
            "source": "interview_analysis",
            "properties": {
                "text": "saw an elderly man with gray hair and blue jacket near the lake",
                "witness_reliability": "high"
            }
        })
        print(f"   ✅ Interview Person: {interview_person_id}")
        
        interview_clue_id = builder.add_clue({
            "name": "Witness Observation",
            "type": "witness_report",
            "description": "Witness saw person matching description",
            "confidence": 0.80,
            "source": "interview_analysis",
            "properties": {
                "section": "witness_saw_person_near_lake",
                "key_terms": ["elderly", "gray hair", "blue jacket", "lake"]
            }
        })
        print(f"   ✅ Interview Clue: {interview_clue_id}")
        
        builder.link_entities(
            interview_person_id, interview_clue_id,
            RelationType.CONNECTED_TO,
            {"relation": "reported"},
            confidence=0.80,
            source="interview_analysis"
        )
        
        print("\n📝 Step 4: Creating Locations")
        print("-" * 60)
        
        # Central Park Lake (main search area)
        lake_location_id = builder.add_location({
            "name": "Central Park Lake",
            "coordinates": {"lat": 40.7829, "lon": -73.9654},
            "terrain_type": "water_body",
            "accessibility": "moderate",
            "confidence": 0.90,
            "source": "gps_data",
            "properties": {
                "area_type": "popular_spot",
                "search_priority": "HIGH"
            }
        })
        print(f"   ✅ Location: {lake_location_id} (Central Park Lake)")
        
        # Central Park Main Entrance
        entrance_location_id = builder.add_location({
            "name": "Central Park Main Entrance",
            "coordinates": {"lat": 40.7829, "lon": -73.9667},
            "terrain_type": "urban",
            "accessibility": "high",
            "confidence": 0.85,
            "source": "gps_data"
        })
        print(f"   ✅ Location: {entrance_location_id} (Main Entrance)")
        
        # Link person to locations
        builder.link_entities(
            person_id, lake_location_id,
            RelationType.LAST_SEEN,
            {"time": "2025-01-10T14:30:00Z", "witness": "park_visitor"},
            confidence=0.90,
            source="emergency_call"
        )
        
        builder.link_entities(
            photo_person_id, lake_location_id,
            RelationType.LAST_SEEN,
            {"time": "2025-01-10T15:20:00Z"},
            confidence=0.85,
            source="photo_analysis"
        )
        
        builder.link_entities(
            interview_person_id, lake_location_id,
            RelationType.LAST_SEEN,
            {"time": "2025-01-10T15:15:00Z"},
            confidence=0.80,
            source="interview_analysis"
        )
        
        builder.link_entities(
            photo_clue_id, lake_location_id,
            RelationType.LOCATED_IN,
            {"discovery_method": "photo_analysis"},
            confidence=0.88,
            source="photo_analysis"
        )
        
        print("\n📝 Step 5: Creating Historical Case Patterns")
        print("-" * 60)
        
        # Current case event
        current_case_id = builder._generate_id("current_case")
        current_case = Entity(
            id=current_case_id,
            type=EntityType.EVENT,
            name="Current SAR Case: John Smith",
            properties={
                "case_type": "current",
                "subject_category": "elderly",
                "medical_condition": "dementia"
            },
            confidence=0.95,
            source="cluemeister"
        )
        kg.add_entity(current_case)
        
        # Link current case to person
        builder.link_entities(
            current_case_id, person_id,
            RelationType.CONNECTED_TO,
            {"relation": "subject"},
            confidence=0.95,
            source="cluemeister"
        )
        
        print(f"   ✅ Current Case: {current_case_id}")
        
        # Historical case 1: Similar case with successful outcome
        hist_case1_id = builder._generate_id("historical_case")
        hist_case1 = Entity(
            id=hist_case1_id,
            type=EntityType.EVENT,
            name="Historical Case 1: Similar Elderly",
            properties={
                "outcome": "found",
                "terrain": "park",
                "subject_category": "elderly",
                "medical_condition": "dementia",
                "found_location": "Central Park Lake"
            },
            confidence=0.85,
            source="history_agent"
        )
        kg.add_entity(hist_case1)
        
        # Historical case 2
        hist_case2_id = builder._generate_id("historical_case")
        hist_case2 = Entity(
            id=hist_case2_id,
            type=EntityType.EVENT,
            name="Historical Case 2: Dementia Patient",
            properties={
                "outcome": "found",
                "terrain": "park",
                "subject_category": "elderly",
                "medical_condition": "dementia",
                "found_location": "Central Park Lake"
            },
            confidence=0.80,
            source="history_agent"
        )
        kg.add_entity(hist_case2)
        
        # Historical case 3: Different outcome
        hist_case3_id = builder._generate_id("historical_case")
        hist_case3 = Entity(
            id=hist_case3_id,
            type=EntityType.EVENT,
            name="Historical Case 3: Other Location",
            properties={
                "outcome": "found",
                "terrain": "urban",
                "subject_category": "elderly",
                "found_location": "Central Park Main Entrance"
            },
            confidence=0.75,
            source="history_agent"
        )
        kg.add_entity(hist_case3)
        
        # Link historical cases to current case
        builder.link_entities(
            current_case_id, hist_case1_id,
            RelationType.SIMILAR_TO,
            {"similarity_reason": "elderly_dementia_park", "similarity_score": 0.85},
            confidence=0.85,
            source="history_agent"
        )
        
        builder.link_entities(
            current_case_id, hist_case2_id,
            RelationType.SIMILAR_TO,
            {"similarity_reason": "elderly_dementia_park", "similarity_score": 0.80},
            confidence=0.80,
            source="history_agent"
        )
        
        builder.link_entities(
            current_case_id, hist_case3_id,
            RelationType.SIMILAR_TO,
            {"similarity_reason": "elderly_park", "similarity_score": 0.70},
            confidence=0.75,
            source="history_agent"
        )
        
        # Link historical cases to success locations
        builder.link_entities(
            hist_case1_id, lake_location_id,
            RelationType.LOCATED_IN,
            {"outcome": "found", "relation": "success_location"},
            confidence=0.90,
            source="history_agent"
        )
        
        builder.link_entities(
            hist_case2_id, lake_location_id,
            RelationType.LOCATED_IN,
            {"outcome": "found", "relation": "success_location"},
            confidence=0.85,
            source="history_agent"
        )
        
        builder.link_entities(
            hist_case3_id, entrance_location_id,
            RelationType.LOCATED_IN,
            {"outcome": "found", "relation": "success_location"},
            confidence=0.80,
            source="history_agent"
        )
        
        print(f"   ✅ Historical Case 1: {hist_case1_id} (Found at Lake)")
        print(f"   ✅ Historical Case 2: {hist_case2_id} (Found at Lake)")
        print(f"   ✅ Historical Case 3: {hist_case3_id} (Found at Entrance)")
        
        print("\n📝 Step 6: Creating Path Analysis Recommendations")
        print("-" * 60)
        
        # Path recommendation
        path_event_id = builder._generate_id("path_analysis")
        path_event = Entity(
            id=path_event_id,
            type=EntityType.EVENT,
            name="Path Analysis: High Priority Route",
            properties={
                "recommended_path": "Main Entrance → Lake",
                "priority": "HIGH",
                "reason": "Shortest path, accessible terrain"
            },
            confidence=0.85,
            source="path_analysis"
        )
        kg.add_entity(path_event)
        
        builder.link_entities(
            path_event_id, lake_location_id,
            RelationType.LOCATED_IN,
            {"recommendation": "high_priority_search_area"},
            confidence=0.85,
            source="path_analysis"
        )
        
        builder.link_entities(
            path_event_id, entrance_location_id,
            RelationType.CONNECTED_TO,
            {"path_segment": "starting_point"},
            confidence=0.80,
            source="path_analysis"
        )
        
        print(f"   ✅ Path Analysis: {path_event_id}")
        
        print("\n📝 Step 7: Creating Additional Clues")
        print("-" * 60)
        
        # Found item clue
        item_clue_id = builder.add_clue({
            "name": "Walking Cane Found",
            "type": "object",
            "description": "Walking cane found near lake shore",
            "found_location": "Central Park Lake",
            "found_time": "2025-01-10T16:00:00Z",
            "reliability": "high",
            "confidence": 0.85,
            "source": "field_search",
            "properties": {
                "item_type": "medical_aid",
                "match_likelihood": 0.90
            }
        })
        
        builder.link_entities(
            item_clue_id, person_id,
            RelationType.OWNS,
            {"item_type": "medical_aid", "match_confidence": 0.90},
            confidence=0.85,
            source="field_search"
        )
        
        builder.link_entities(
            item_clue_id, lake_location_id,
            RelationType.LOCATED_IN,
            {"discovery_location": "lake_shore"},
            confidence=0.85,
            source="field_search"
        )
        
        print(f"   ✅ Clue: {item_clue_id} (Walking Cane)")
        
        # Generate insights
        print("\n📊 Generating Graph Insights...")
        insights = kg.generate_insights()
        
        print(f"\n✅ Demo Graph Created Successfully!")
        print(f"\n📊 Graph Statistics:")
        print(f"   Total Entities: {insights.get('total_entities', 0)}")
        print(f"   Total Relations: {insights.get('total_relations', 0)}")
        print(f"   Entity Types: {insights.get('entity_types', {})}")
        
        print(f"\n🎨 Visualization Instructions:")
        print(f"   1. Open Neo4j Browser: http://localhost:7474")
        print(f"   2. Login: neo4j / password")
        print(f"   3. Run this query to see the full graph:")
        print(f"\n   MATCH (n:Entity)")
        print(f"   OPTIONAL MATCH (n)-[r]->(m:Entity)")
        print(f"   RETURN n, r, m")
        print(f"   LIMIT 50")
        
        print(f"\n   4. Or see just the main connections:")
        print(f"\n   MATCH path = (person:Person)-[*1..3]-(related:Entity)")
        print(f"   WHERE person.name CONTAINS 'John Smith' OR person.name CONTAINS 'Photo'")
        print(f"   RETURN path")
        print(f"   LIMIT 25")
        
        print(f"\n   5. See historical patterns:")
        print(f"\n   MATCH (current:Event)-[:SIMILAR_TO]->(hist:Event)")
        print(f"   MATCH (hist)-[:LOCATED_IN]->(loc:Location)")
        print(f"   RETURN current, hist, loc")
        
        print(f"\n💡 Tips for PPT:")
        print(f"   - Use Neo4j Browser's screenshot feature")
        print(f"   - Adjust node colors and sizes in browser settings")
        print(f"   - Export as PNG from browser")
        print(f"   - Focus on showing: Person → Location → Historical Cases connections")
        
        kg.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create demo graph: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_demo_graph()
    sys.exit(0 if success else 1)







