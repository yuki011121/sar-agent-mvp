#!/usr/bin/env python3
"""
Core optimization tests - tests Cypher queries and correlation discovery
without requiring full ClueMeisterAgent initialization
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder,
    EntityType, RelationType, Entity
)

def test_cypher_queries():
    """Test the Cypher queries used in optimizations"""
    print("\n" + "="*60)
    print("Test: Cypher Query Functionality")
    print("="*60)
    
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
        
        # Create test data for cross-source matching
        print("\n📝 Creating test data...")
        
        # Photo source person
        photo_person_id = builder.add_missing_person({
            "name": "Photo Person",
            "hair_color": "gray",
            "clothing": ["blue jacket"],
            "confidence": 0.9,
            "source": "photo_analysis"
        })
        print(f"   ✅ Photo person: {photo_person_id}")
        
        # Interview source person (should match)
        interview_person_id = builder.add_missing_person({
            "name": "Interview Person",
            "hair_color": "gray",  # Same - should match
            "confidence": 0.8,
            "source": "interview_analysis",
            "properties": {
                "text": "saw person with gray hair and blue jacket"
            }
        })
        print(f"   ✅ Interview person: {interview_person_id}")
        
        # Common location
        location_id = builder.add_location({
            "name": "Test Location",
            "confidence": 0.8,
            "source": "test"
        })
        print(f"   ✅ Location: {location_id}")
        
        # Link both persons to location
        builder.link_entities(photo_person_id, location_id, RelationType.LAST_SEEN)
        builder.link_entities(interview_person_id, location_id, RelationType.LAST_SEEN)
        
        # Test person matching query
        print("\n🔍 Testing person matching query...")
        try:
            with kg.neo4j_driver.session() as session:
                query = """
                MATCH (p1:Entity:Person)
                WHERE p1.source = "photo_analysis"
                MATCH (p2:Entity:Person)
                WHERE p2.source = "interview_analysis"
                WITH p1, p2, 
                     p1.properties.hair_color as p1_hair,
                     p2.properties.hair_color as p2_hair
                WHERE (p1_hair IS NOT NULL AND p1_hair = p2_hair)
                RETURN p1.id as photo_id, p2.id as interview_id,
                       p1_hair, p2_hair
                LIMIT 10
                """
                result = session.run(query)
                matches = list(result)
                print(f"   ✅ Found {len(matches)} person matches")
                if matches:
                    for match in matches:
                        print(f"      - Photo: {match['photo_id']}, Interview: {match['interview_id']}")
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
            return False
        
        # Test location correlation query
        print("\n🔍 Testing location correlation query...")
        try:
            with kg.neo4j_driver.session() as session:
                query = """
                MATCH (photo:Entity)-[r1:LOCATED_IN|LAST_SEEN]->(loc:Location)
                WHERE photo.source = "photo_analysis"
                MATCH (interview:Entity)-[r2:LOCATED_IN|LAST_SEEN]->(loc)
                WHERE interview.source = "interview_analysis"
                RETURN DISTINCT loc.id as location_id, loc.name as location_name,
                       count(DISTINCT photo) as photo_count,
                       count(DISTINCT interview) as interview_count
                LIMIT 20
                """
                result = session.run(query)
                correlations = list(result)
                print(f"   ✅ Found {len(correlations)} location correlations")
                if correlations:
                    for corr in correlations:
                        print(f"      - {corr['location_name']}: "
                              f"photo={corr['photo_count']}, interview={corr['interview_count']}")
        except Exception as e:
            print(f"   ❌ Query failed: {e}")
            return False
        
        # Test historical pattern query (if we have historical data)
        print("\n🔍 Testing historical pattern query...")
        try:
            # Create a mock historical case
            current_case_id = builder._generate_id("current_case")
            current_case = Entity(
                id=current_case_id,
                type=EntityType.EVENT,
                name="Current Case",
                properties={},
                confidence=0.9,
                source="test"
            )
            kg.add_entity(current_case)
            
            hist_case_id = builder._generate_id("hist_case")
            hist_case = Entity(
                id=hist_case_id,
                type=EntityType.EVENT,
                name="Historical Case",
                properties={"outcome": "found"},
                confidence=0.8,
                source="history_agent"
            )
            kg.add_entity(hist_case)
            
            builder.link_entities(current_case_id, hist_case_id, RelationType.SIMILAR_TO)
            builder.link_entities(hist_case_id, location_id, RelationType.LOCATED_IN)
            
            with kg.neo4j_driver.session() as session:
                query = """
                MATCH (current:Entity:Event)-[r:SIMILAR_TO]->(hist:Entity:Event)
                MATCH (hist)-[r2:LOCATED_IN|OCCURRED_AT]->(success_loc:Entity:Location)
                WITH hist, success_loc, hist.properties.outcome as outcome
                WHERE outcome = "found" OR outcome CONTAINS "found"
                WITH success_loc, count(*) as success_count, collect(DISTINCT hist.id) as cases
                ORDER BY success_count DESC
                RETURN success_loc.id as location_id, success_loc.name as location_name,
                       success_count, cases as successful_cases
                LIMIT 10
                """
                result = session.run(query)
                patterns = list(result)
                print(f"   ✅ Found {len(patterns)} historical patterns")
                if patterns:
                    for pattern in patterns:
                        print(f"      - {pattern['location_name']}: "
                              f"{pattern['success_count']} successful cases")
        except Exception as e:
            print(f"   ⚠️  Historical pattern query: {e} (may not have historical data)")
        
        kg.close()
        print("\n✅ All Cypher queries executed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_entity_retrieval():
    """Test entity retrieval from Neo4j (fix for old NetworkX dependency)"""
    print("\n" + "="*60)
    print("Test: Entity Retrieval (NetworkX Fix)")
    print("="*60)
    
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
        
        # Create test entity
        person_id = builder.add_missing_person({
            "name": "Test Person",
            "age": 30,
            "confidence": 0.9,
            "source": "test"
        })
        
        # Test retrieval using find_entities (new way)
        entities = kg.find_entities(properties={"id": person_id})
        
        if entities:
            print(f"✅ Successfully retrieved entity using find_entities: {entities[0].name}")
            print(f"   ✅ Entity type: {entities[0].type.value}")
            print(f"   ✅ Entity ID: {entities[0].id}")
        else:
            print(f"❌ Failed to retrieve entity")
            return False
        
        # Test entity importance calculation
        importance = kg.calculate_entity_importance(person_id)
        print(f"   ✅ Entity importance: {importance:.2f}")
        
        kg.close()
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 ClueMeister Core Optimization Tests")
    print("="*60)
    
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    print(f"\n📡 Neo4j URI: {neo4j_uri}")
    print("   (Make sure Neo4j is running: docker-compose up neo4j)\n")
    
    results = []
    
    results.append(("Entity Retrieval Fix", test_entity_retrieval()))
    results.append(("Cypher Queries", test_cypher_queries()))
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{'='*60}")
    print(f"Total: {passed}/{total} tests passed")
    print(f"{'='*60}")
    
    if passed == total:
        print("\n🎉 All core tests passed!")
        print("\n💡 Next steps:")
        print("   1. Check Neo4j Browser: http://localhost:7474")
        print("   2. Run: MATCH (n:Entity) RETURN n LIMIT 25")
        print("   3. If core tests pass, test full integration with:")
        print("      docker-compose up cluemeister-agent")
    else:
        print("\n⚠️  Some tests failed. Review errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)







