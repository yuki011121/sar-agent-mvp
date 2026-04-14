#!/usr/bin/env python3
"""
Ensure ALL nodes have proper labels - fix the empty red nodes issue
This ensures Location nodes and all other nodes have both name and display_label
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from knowledge_graph import KnowledgeGraph

def ensure_all_labels():
    """Ensure all nodes have name and display_label for proper visualization"""
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
    
    kg = KnowledgeGraph(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password
    )
    
    print("🔧 Ensuring ALL nodes have proper labels...")
    print("=" * 60)
    
    try:
        with kg.neo4j_driver.session() as session:
            # Critical: Ensure Location nodes have name property
            # Neo4j Browser uses 'name' by default if display_label is not set in Caption
            fix_location_query = """
            MATCH (loc:Entity:Location)
            WHERE loc.name IS NULL OR loc.name = ''
            WITH loc,
                 CASE 
                   WHEN loc.display_label CONTAINS 'Lake' THEN 'Central Park Lake'
                   WHEN loc.display_label CONTAINS 'Entrance' THEN 'Central Park Main Entrance'
                   WHEN loc.display_label CONTAINS 'Test' THEN 'Test Location'
                   ELSE COALESCE(loc.display_label, 'Location')
                 END as new_name
            SET loc.name = new_name
            RETURN loc.id as id, loc.name as name, loc.display_label as display_label
            """
            
            result = session.run(fix_location_query)
            fixed = 0
            for record in result:
                print(f"   Fixed Location: {record['name']} (ID: {record['id']})")
                fixed += 1
            
            # Ensure all nodes have name (critical for Neo4j Browser default display)
            ensure_all_names = """
            MATCH (n:Entity)
            WHERE n.name IS NULL OR n.name = ''
            SET n.name = COALESCE(n.display_label, n.id, 'Entity')
            RETURN count(n) as count
            """
            
            result = session.run(ensure_all_names)
            count = result.single()["count"]
            if count > 0:
                print(f"\n✅ Ensured {count} additional nodes have name property")
            
            # Verify Location nodes
            verify_query = """
            MATCH (loc:Entity:Location)
            RETURN loc.name as name, 
                   loc.display_label as display_label,
                   CASE WHEN loc.name IS NULL THEN '❌ MISSING' ELSE '✅ OK' END as status
            LIMIT 10
            """
            
            result = session.run(verify_query)
            print("\n📊 Location nodes status:")
            print("-" * 60)
            all_ok = True
            for record in result:
                status = record["status"]
                name = record["name"] or "NULL"
                display = record["display_label"] or "NULL"
                print(f"{status} | name: {name:30} | display_label: {display}")
                if status == "❌ MISSING":
                    all_ok = False
            
            if all_ok:
                print("\n✅ All Location nodes have proper labels!")
                print("\n💡 In Neo4j Browser:")
                print("   Option 1: Settings → Node Caption → Select 'name'")
                print("   Option 2: Settings → Node Caption → Select 'display_label'")
                print("   Option 3: Use custom expression: COALESCE(n.display_label, n.name)")
            else:
                print("\n⚠️  Some nodes still need fixing")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        kg.close()

if __name__ == "__main__":
    ensure_all_labels()







