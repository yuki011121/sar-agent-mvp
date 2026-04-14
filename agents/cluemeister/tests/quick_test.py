#!/usr/bin/env python3
"""
Quick test for Neo4j Knowledge Graph
Tests basic functionality without requiring full agent setup
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder,
    EntityType, RelationType, Entity
)

def main():
    print("🚀 ClueMeister Knowledge Graph Quick Test")
    print("=" * 50)
    
    # Get Neo4j connection info
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    print(f"\n📡 Connecting to Neo4j at {neo4j_uri}...")
    
    try:
        # Create knowledge graph
        kg = KnowledgeGraph(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password
        )
        print("✅ Connected to Neo4j successfully!")
        
        builder = ClueMeisterGraphBuilder(kg)
        
        # Test 1: Add entities
        print("\n📝 Test 1: Adding entities...")
        
        person_id = builder.add_missing_person({
            "name": "John Doe",
            "age": 65,
            "gender": "male",
            "hair_color": "gray",
            "confidence": 0.9,
            "source": "test"
        })
        print(f"   ✅ Added person: {person_id}")
        
        location_id = builder.add_location({
            "name": "Central Park Lake",
            "coordinates": {"lat": 40.7829, "lon": -73.9654},
            "confidence": 0.8,
            "source": "test"
        })
        print(f"   ✅ Added location: {location_id}")
        
        clue_id = builder.add_clue({
            "name": "Blue Jacket Found",
            "type": "clothing",
            "description": "Blue jacket found near the lake",
            "confidence": 0.85,
            "source": "test"
        })
        print(f"   ✅ Added clue: {clue_id}")
        
        # Test 2: Add relations
        print("\n🔗 Test 2: Adding relations...")
        
        rel1_id = builder.link_entities(
            person_id, location_id,
            RelationType.LAST_SEEN,
            {"time": "2025-01-05T14:30:00Z"},
            confidence=0.8,
            source="test"
        )
        print(f"   ✅ Added relation: {rel1_id}")
        
        rel2_id = builder.link_entities(
            clue_id, person_id,
            RelationType.OWNS,
            {"match_confidence": 0.9},
            confidence=0.85,
            source="test"
        )
        print(f"   ✅ Added relation: {rel2_id}")
        
        # Test 3: Query entities
        print("\n🔍 Test 3: Querying entities...")
        entities = kg.find_entities(entity_type=EntityType.PERSON)
        print(f"   ✅ Found {len(entities)} person entities")
        
        # Test 4: Query relations
        relations = kg.find_relations()
        print(f"   ✅ Found {len(relations)} relations")
        
        # Test 5: Find paths
        print("\n🛤️  Test 4: Finding paths...")
        paths = kg.find_paths(person_id, location_id, max_length=3)
        print(f"   ✅ Found {len(paths)} paths")
        
        # Test 6: Generate insights
        print("\n📊 Test 5: Generating insights...")
        insights = kg.generate_insights()
        print(f"   ✅ Total entities: {insights['total_entities']}")
        print(f"   ✅ Total relations: {insights['total_relations']}")
        print(f"   ✅ Entity types: {insights['entity_types']}")
        
        # Close connection
        kg.close()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("\n📊 View results in Neo4j Browser:")
        print("   http://localhost:7474")
        print("   (username: neo4j, password: password)")
        print("\n💡 Try this query in Neo4j Browser:")
        print("   MATCH (n:Entity) RETURN n LIMIT 25")
        print("=" * 50)
        
    except ImportError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("💡 Install dependencies:")
        print("   pip install neo4j python-dotenv")
        sys.exit(1)
    except ConnectionError as e:
        print(f"\n❌ Failed to connect to Neo4j: {e}")
        print("💡 Make sure Neo4j is running:")
        print("   docker-compose up neo4j")
        print("   # Wait 15-20 seconds for Neo4j to start")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()







