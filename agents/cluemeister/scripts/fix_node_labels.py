#!/usr/bin/env python3
"""
Fix node labels for better visualization
Adds short, readable labels to all nodes
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import KnowledgeGraph

def fix_labels():
    """Add short display labels to nodes"""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    kg = KnowledgeGraph(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password
    )
    
    print("🔧 Fixing node labels for better visualization...")
    print("=" * 60)
    
    try:
        with kg.neo4j_driver.session() as session:
            # Update all nodes with short labels
            query = """
            MATCH (n:Entity)
            WITH n,
                 CASE 
                   WHEN n.name CONTAINS 'John Smith' THEN 'John Smith'
                   WHEN n.name CONTAINS 'Photo Detection' THEN '📷 Photo'
                   WHEN n.name CONTAINS 'Photo Person' THEN '📷 Photo'
                   WHEN n.name CONTAINS 'Witness Report' THEN '👤 Witness'
                   WHEN n.name CONTAINS 'Interview Person' THEN '💬 Interview'
                   WHEN n.name CONTAINS 'Central Park Lake' THEN '🏞️ Lake'
                   WHEN n.name CONTAINS 'Central Park Main' THEN '🚪 Entrance'
                   WHEN n.name CONTAINS 'Test Location' THEN '📍 Test Loc'
                   WHEN n.name CONTAINS 'Historical Case 1' THEN '📚 Case 1'
                   WHEN n.name CONTAINS 'Historical Case 2' THEN '📚 Case 2'
                   WHEN n.name CONTAINS 'Historical Case 3' THEN '📚 Case 3'
                   WHEN n.name CONTAINS 'Current SAR Case' THEN '🎯 Current'
                   WHEN n.name CONTAINS 'Path Analysis' THEN '🛤️ Path'
                   WHEN n.name CONTAINS 'Blue Jacket' THEN '🧥 Blue Jacket'
                   WHEN n.name CONTAINS 'Walking Cane' THEN '🦯 Cane'
                   WHEN n.name CONTAINS 'Witness Observation' THEN '👁️ Witness Clue'
                   ELSE SUBSTRING(n.name, 0, 15)
                 END as short_label
            SET n.display_label = short_label
            RETURN n.name as original, n.display_label as short_label, n.type as type
            ORDER BY n.type, n.name
            """
            
            result = session.run(query)
            updated = 0
            print("\n✅ Updated node labels:")
            for record in result:
                print(f"   {record['type']:15} | {record['original'][:30]:30} → {record['short_label']}")
                updated += 1
            
            print(f"\n📊 Total updated: {updated} nodes")
            print("\n💡 Now in Neo4j Browser:")
            print("   1. Go to Settings (gear icon)")
            print("   2. Node Caption → Select 'display_label'")
            print("   3. Or use this query with display_label:")
            
            print("\n" + "=" * 60)
            print("OPTIMIZED QUERY FOR GRAPH 1:")
            print("=" * 60)
            print("""
MATCH (photo:Person {source: 'photo_analysis'})
MATCH (interview:Person {source: 'interview_analysis'})
MATCH (photo)-[r1:LAST_SEEN]->(loc:Location)<-[r2:LAST_SEEN]-(interview)
RETURN photo.display_label as Photo,
       interview.display_label as Interview,
       loc.display_label as Location,
       photo, interview, loc, r1, r2
            """)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        kg.close()

if __name__ == "__main__":
    fix_labels()







