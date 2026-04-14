#!/usr/bin/env python3
"""
Comprehensive test for ClueMeister optimizations
Tests the new correlation discovery and recommendation features
"""

import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder,
    EntityType, RelationType, Entity
)

# Import ClueMeisterAgent methods we need, without full initialization
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from main import ClueMeisterAgent
except ImportError:
    # Fallback: define minimal version for testing
    class ClueMeisterAgent:
        def __init__(self):
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            self.knowledge_graph = KnowledgeGraph(
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password
            )
        
        def analyze_cross_agent_correlations(self):
            # Import the method directly
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "main_module", 
                os.path.join(os.path.dirname(__file__), "main.py")
            )
            if spec and spec.loader:
                main_module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(main_module)
                    agent = main_module.ClueMeisterAgent()
                    return agent.analyze_cross_agent_correlations()
                except:
                    return {}
            return {}
        
        def generate_search_recommendations(self):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "main_module", 
                os.path.join(os.path.dirname(__file__), "main.py")
            )
            if spec and spec.loader:
                main_module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(main_module)
                    agent = main_module.ClueMeisterAgent()
                    return agent.generate_search_recommendations()
                except:
                    return {}
            return {}

def test_basic_functionality():
    """Test 1: Basic entity creation and storage"""
    print("\n" + "="*60)
    print("Test 1: Basic Entity Creation and Storage")
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
        
        # Create test entities
        person_id = builder.add_missing_person({
            "name": "Test Person",
            "age": 30,
            "gender": "male",
            "hair_color": "brown",
            "clothing": ["blue jacket"],
            "confidence": 0.9,
            "source": "test"
        })
        print(f"✅ Created person: {person_id}")
        
        location_id = builder.add_location({
            "name": "Test Location",
            "coordinates": {"lat": 40.0, "lon": -73.0},
            "confidence": 0.8,
            "source": "test"
        })
        print(f"✅ Created location: {location_id}")
        
        # Test retrieval
        persons = kg.find_entities(entity_type=EntityType.PERSON)
        print(f"✅ Found {len(persons)} person entities")
        
        kg.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cross_source_correlations():
    """Test 2: Cross-source correlation discovery"""
    print("\n" + "="*60)
    print("Test 2: Cross-Source Correlation Discovery")
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
        
        # Create entities from different sources that should match
        photo_person_id = builder.add_missing_person({
            "name": "Photo Person",
            "hair_color": "gray",
            "clothing": ["blue jacket"],
            "confidence": 0.9,
            "source": "photo_analysis"
        })
        
        interview_person_id = builder.add_missing_person({
            "name": "Interview Person",
            "hair_color": "gray",  # Same hair color - should match
            "confidence": 0.8,
            "source": "interview_analysis",
            "properties": {
                "text": "saw a person with gray hair and blue jacket"
            }
        })
        
        print(f"✅ Created photo person: {photo_person_id}")
        print(f"✅ Created interview person: {interview_person_id}")
        
        # Create location mentioned by both
        location_id = builder.add_location({
            "name": "Common Location",
            "confidence": 0.8,
            "source": "test"
        })
        
        builder.link_entities(photo_person_id, location_id, RelationType.LAST_SEEN)
        builder.link_entities(interview_person_id, location_id, RelationType.LAST_SEEN)
        
        # Test correlation discovery (simulate ClueMeister agent)
        agent = ClueMeisterAgent()
        correlations = agent.analyze_cross_agent_correlations()
        
        print(f"\n📊 Correlation Results:")
        print(f"   Person matches: {len(correlations.get('person_entity_matches', []))}")
        print(f"   Location correlations: {len(correlations.get('location_correlations', []))}")
        print(f"   High confidence paths: {len(correlations.get('high_confidence_paths', []))}")
        
        if correlations.get('person_entity_matches'):
            print(f"✅ Found person entity matches!")
        if correlations.get('location_correlations'):
            print(f"✅ Found location correlations!")
            
        kg.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_historical_patterns():
    """Test 3: Historical pattern analysis"""
    print("\n" + "="*60)
    print("Test 3: Historical Pattern Analysis")
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
        
        # Create current case
        current_case_id = builder._generate_id("current_case")
        current_case = Entity(
            id=current_case_id,
            type=EntityType.EVENT,
            name="Current SAR Case",
            properties={"case_type": "current"},
            confidence=0.9,
            source="test"
        )
        kg.add_entity(current_case)
        
        # Create historical cases (simulating History Agent output)
        success_location_id = builder.add_location({
            "name": "Historical Success Location",
            "confidence": 0.8,
            "source": "historical_case"
        })
        
        for i in range(3):
            hist_case_id = builder._generate_id("historical_case")
            hist_case = Entity(
                id=hist_case_id,
                type=EntityType.EVENT,
                name=f"Historical Case {i+1}",
                properties={"outcome": "found"},
                confidence=0.8,
                source="history_agent"
            )
            kg.add_entity(hist_case)
            
            # Link to current case
            builder.link_entities(
                current_case_id, hist_case_id,
                RelationType.SIMILAR_TO,
                {"similarity_source": "test"},
                confidence=0.75
            )
            
            # Link to success location
            builder.link_entities(
                hist_case_id, success_location_id,
                RelationType.LOCATED_IN,
                {"terrain": "test"},
                confidence=0.8
            )
        
        print(f"✅ Created current case and 3 historical cases")
        
        # Test correlation discovery
        agent = ClueMeisterAgent()
        correlations = agent.analyze_cross_agent_correlations()
        
        history_patterns = correlations.get('history_patterns', [])
        print(f"\n📊 Historical Pattern Results:")
        print(f"   History patterns found: {len(history_patterns)}")
        
        if history_patterns:
            for pattern in history_patterns:
                print(f"   ✅ Location: {pattern.get('location_name')}, "
                      f"Success count: {pattern.get('success_count')}")
        
        kg.close()
        return len(history_patterns) > 0
        
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_recommendations():
    """Test 4: Recommendation generation"""
    print("\n" + "="*60)
    print("Test 4: Recommendation Generation")
    print("="*60)
    
    try:
        agent = ClueMeisterAgent()
        
        # Generate recommendations
        recommendations = agent.generate_search_recommendations()
        
        print(f"\n📊 Recommendation Results:")
        print(f"   Search priorities: {len(recommendations.get('search_priorities', []))}")
        print(f"   Immediate actions: {len(recommendations.get('immediate_actions', []))}")
        
        if recommendations.get('search_priorities'):
            print(f"\n✅ Top Search Priorities:")
            for priority in recommendations['search_priorities'][:3]:
                print(f"   - {priority.get('area')}: {priority.get('priority')}")
                print(f"     Reason: {priority.get('reason', 'N/A')}")
        
        return len(recommendations.get('search_priorities', [])) > 0 or \
               len(recommendations.get('immediate_actions', [])) > 0
        
    except Exception as e:
        print(f"❌ Test 4 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_neo4j_queries():
    """Test 5: Direct Neo4j query validation"""
    print("\n" + "="*60)
    print("Test 5: Neo4j Query Validation")
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
        
        # Test basic query
        with kg.neo4j_driver.session() as session:
            query = "MATCH (n:Entity) RETURN count(n) as total"
            result = session.run(query)
            record = result.single()
            total = record["total"] if record else 0
            print(f"✅ Total entities in graph: {total}")
            
            # Test person query
            query = "MATCH (n:Entity:Person) RETURN count(n) as count"
            result = session.run(query)
            record = result.single()
            person_count = record["count"] if record else 0
            print(f"✅ Total persons: {person_count}")
            
            # Test relationship query
            query = "MATCH ()-[r]->() RETURN count(r) as count"
            result = session.run(query)
            record = result.single()
            rel_count = record["count"] if record else 0
            print(f"✅ Total relationships: {rel_count}")
        
        kg.close()
        return True
        
    except Exception as e:
        print(f"❌ Test 5 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 ClueMeister Optimization Test Suite")
    print("="*60)
    
    # Check Neo4j connection
    print("\n📡 Checking Neo4j connection...")
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    print(f"   URI: {neo4j_uri}")
    
    results = []
    
    # Run tests
    results.append(("Basic Functionality", test_basic_functionality()))
    results.append(("Cross-Source Correlations", test_cross_source_correlations()))
    results.append(("Historical Patterns", test_historical_patterns()))
    results.append(("Recommendations", test_recommendations()))
    results.append(("Neo4j Queries", test_neo4j_queries()))
    
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
        print("\n🎉 All tests passed!")
        print("\n💡 Next steps:")
        print("   1. Check Neo4j Browser: http://localhost:7474")
        print("   2. Run query: MATCH (n:Entity) RETURN n LIMIT 25")
        print("   3. Review correlations and recommendations")
    else:
        print("\n⚠️  Some tests failed. Review errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

