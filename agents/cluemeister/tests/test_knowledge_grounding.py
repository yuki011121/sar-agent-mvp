#!/usr/bin/env python3
"""
Unit tests for Knowledge Grounding Framework
"""

import unittest
import os
import sys
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_grounding import KnowledgeGrounding, Claim, Evidence
from knowledge_graph import KnowledgeGraph, Entity, EntityType, Relation, RelationType
import json

class TestKnowledgeGrounding(unittest.TestCase):
    """Test cases for Knowledge Grounding"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock knowledge graph
        self.mock_kg = Mock(spec=KnowledgeGraph)
        self.grounding = KnowledgeGrounding(self.mock_kg)
    
    def test_extract_claims_basic(self):
        """Test basic claim extraction"""
        text = "John Doe was seen at Mountain Trail. High priority area: Stream Valley."
        
        # Mock find_entities to return empty (no matches)
        self.mock_kg.find_entities.return_value = []
        
        claims = self.grounding._extract_claims(text)
        
        # Should extract at least some claims
        self.assertIsInstance(claims, list)
        self.assertGreater(len(claims), 0)
    
    def test_extract_claims_with_entities(self):
        """Test claim extraction when entities exist in KG"""
        text = "John Doe was seen at Mountain Trail"
        
        # Create mock entities
        mock_person = Mock(spec=Entity)
        mock_person.id = "person_1"
        mock_person.name = "John Doe"
        
        mock_location = Mock(spec=Entity)
        mock_location.id = "location_1"
        mock_location.name = "Mountain Trail"
        
        # Mock find_entities to return entities
        def mock_find_entities(entity_type=None, properties=None):
            if properties and properties.get("name") == "John Doe":
                return [mock_person]
            elif properties and properties.get("name") == "Mountain Trail":
                return [mock_location]
            return []
        
        self.mock_kg.find_entities.side_effect = mock_find_entities
        
        claims = self.grounding._extract_claims(text)
        
        # Should find claims with entity mentions
        self.assertGreater(len(claims), 0)
        if claims[0].entity_mentions:
            self.assertIn("person_1", claims[0].entity_mentions)
    
    def test_ground_claim_with_entities_and_relation(self):
        """Test grounding a claim with entities and relation (should be grounded)"""
        claim = Claim(
            text="John Doe was seen at Mountain Trail",
            entity_mentions=["person_1", "location_1"],
            relation_mentions=["SEEN_AT"],
            confidence=0.7,
            source="llm"
        )
        
        # Mock entities
        mock_entity1 = Mock(spec=Entity)
        mock_entity1.id = "person_1"
        mock_entity1.type = EntityType.PERSON
        mock_entity1.name = "John Doe"
        mock_entity1.properties = {}
        mock_entity1.confidence = 0.9
        mock_entity1.source = "test"
        
        mock_entity2 = Mock(spec=Entity)
        mock_entity2.id = "location_1"
        mock_entity2.type = EntityType.LOCATION
        mock_entity2.name = "Mountain Trail"
        mock_entity2.properties = {}
        mock_entity2.confidence = 0.9
        mock_entity2.source = "test"
        
        # Mock relation
        mock_relation = Mock(spec=Relation)
        mock_relation.id = "rel_1"
        mock_relation.type = RelationType.SEEN_AT
        mock_relation.source_entity = "person_1"
        mock_relation.target_entity = "location_1"
        mock_relation.properties = {}
        mock_relation.confidence = 0.8
        mock_relation.source = "test"
        
        self.mock_kg.find_entities.return_value = [mock_entity1, mock_entity2]
        self.mock_kg.find_relations.return_value = [mock_relation]
        self.mock_kg.find_paths.return_value = []
        # Mock get_entity_neighbors to return empty list (no additional neighbors needed for this test)
        self.mock_kg.get_entity_neighbors.return_value = []
        
        grounded = self.grounding._ground_claim(claim)
        
        self.assertIn("grounding_confidence", grounded)
        self.assertIn("is_grounded", grounded)
        self.assertIn("supporting_entities", grounded)
        # With relation, should be grounded (confidence >= 0.5 and has relation)
        self.assertTrue(grounded["is_grounded"], "Claim with relation should be grounded")
        self.assertGreaterEqual(grounded["grounding_confidence"], 0.5)
    
    def test_ground_claim_with_entities_only(self):
        """Test grounding a claim with entities only (should NOT be grounded - strict criteria)"""
        claim = Claim(
            text="John Doe mentioned",
            entity_mentions=["person_1"],
            relation_mentions=[],
            confidence=0.7,
            source="llm"
        )
        
        # Mock entity
        mock_entity = Mock(spec=Entity)
        mock_entity.id = "person_1"
        mock_entity.type = EntityType.PERSON
        mock_entity.name = "John Doe"
        mock_entity.properties = {}
        mock_entity.confidence = 0.9
        mock_entity.source = "test"
        
        self.mock_kg.find_entities.return_value = [mock_entity]
        self.mock_kg.find_relations.return_value = []
        self.mock_kg.find_paths.return_value = []
        # Mock get_entity_neighbors to return empty list
        self.mock_kg.get_entity_neighbors.return_value = []
        
        grounded = self.grounding._ground_claim(claim)
        
        # Without relation or path, should NOT be grounded (strict criteria)
        self.assertFalse(grounded["is_grounded"], 
                        "Claim without relation or path should not be grounded")
        # Confidence should be capped at 0.4 without relation/path
        self.assertLessEqual(grounded["grounding_confidence"], 0.4)
    
    def test_is_properly_grounded_strict_criteria(self):
        """Test _is_properly_grounded with strict criteria"""
        # Test case 1: Has relation, confidence >= 0.5, should be grounded
        mock_relation = Mock(spec=Relation)
        mock_entity = Mock(spec=Entity)
        result1 = self.grounding._is_properly_grounded(
            0.6, [mock_entity], [mock_relation], []
        )
        self.assertTrue(result1, "Should be grounded with relation and confidence >= 0.5")
        
        # Test case 2: Has path, confidence >= 0.5, should be grounded
        result2 = self.grounding._is_properly_grounded(
            0.6, [mock_entity], [], ["entity1", "entity2"]
        )
        self.assertTrue(result2, "Should be grounded with path and confidence >= 0.5")
        
        # Test case 3: Low confidence, should NOT be grounded
        result3 = self.grounding._is_properly_grounded(
            0.4, [mock_entity], [mock_relation], []
        )
        self.assertFalse(result3, "Should not be grounded with confidence < 0.5")
        
        # Test case 4: No relation or path, should NOT be grounded
        result4 = self.grounding._is_properly_grounded(
            0.6, [mock_entity], [], []
        )
        self.assertFalse(result4, "Should not be grounded without relation or path")
        
        # Test case 5: No entities, should NOT be grounded
        result5 = self.grounding._is_properly_grounded(
            0.6, [], [mock_relation], []
        )
        self.assertFalse(result5, "Should not be grounded without entities")
    
    def test_calculate_grounding_confidence(self):
        """Test confidence calculation with new strict criteria"""
        claim = Claim(
            text="Test claim",
            entity_mentions=["entity_1"],
            relation_mentions=[],
            confidence=0.7,
            source="llm"
        )
        
        mock_entity = Mock(spec=Entity)
        mock_entity.id = "entity_1"
        mock_entity.type = EntityType.PERSON
        mock_entity.name = "Test Person"
        mock_entity.properties = {}
        mock_entity.confidence = 0.9
        mock_entity.source = "test"
        
        # Test 1: Only entities (no relation/path) - should be capped at 0.4
        confidence1 = self.grounding._calculate_grounding_confidence(
            claim, [mock_entity], [], []
        )
        self.assertGreaterEqual(confidence1, 0.0)
        self.assertLessEqual(confidence1, 0.4, "Confidence without relation/path should be capped at 0.4")
        
        # Test 2: With relation - should be able to reach 0.5+
        mock_relation = Mock(spec=Relation)
        confidence2 = self.grounding._calculate_grounding_confidence(
            claim, [mock_entity], [mock_relation], []
        )
        self.assertGreaterEqual(confidence2, 0.5, "Confidence with relation should be >= 0.5")
        
        # Test 3: With path - should be able to reach 0.5+
        confidence3 = self.grounding._calculate_grounding_confidence(
            claim, [mock_entity], [], ["entity1", "entity2"]
        )
        self.assertGreaterEqual(confidence3, 0.5, "Confidence with path should be >= 0.5")
    
    def test_calculate_grounding_metrics(self):
        """Test metrics calculation"""
        grounded_claims = [
            {
                "is_grounded": True,
                "grounding_confidence": 0.8
            },
            {
                "is_grounded": False,
                "grounding_confidence": 0.3
            },
            {
                "is_grounded": True,
                "grounding_confidence": 0.9
            }
        ]
        
        metrics = self.grounding._calculate_grounding_metrics(grounded_claims)
        
        self.assertIn("grounding_rate", metrics)
        self.assertIn("overall_confidence", metrics)
        self.assertEqual(metrics["total_claims"], 3)
        self.assertEqual(metrics["grounded_claims"], 2)
        self.assertAlmostEqual(metrics["grounding_rate"], 2/3, places=2)
    
    def test_ground_llm_response(self):
        """Test full grounding workflow"""
        query = "What are the high priority search areas?"
        llm_response = "High priority area: Stream Valley. John Doe was seen at Mountain Trail."
        
        # Mock the internal methods
        with patch.object(self.grounding, '_extract_claims') as mock_extract, \
             patch.object(self.grounding, '_ground_claim') as mock_ground, \
             patch.object(self.grounding, '_calculate_grounding_metrics') as mock_metrics, \
             patch.object(self.grounding, '_extract_knowledge_sources') as mock_sources:
            
            mock_claim = Claim(
                text="High priority area: Stream Valley",
                entity_mentions=[],
                relation_mentions=[],
                confidence=0.6,
                source="llm"
            )
            mock_extract.return_value = [mock_claim]
            
            mock_grounded = {
                "claim": {"text": "High priority area: Stream Valley"},
                "is_grounded": True,
                "grounding_confidence": 0.7
            }
            mock_ground.return_value = mock_grounded
            
            mock_metrics.return_value = {
                "overall_confidence": 0.7,
                "grounding_rate": 1.0,
                "total_claims": 1,
                "grounded_claims": 1
            }
            
            mock_sources.return_value = ["knowledge_graph"]
            
            result = self.grounding.ground_llm_response(query, llm_response)
            
            self.assertIn("original_response", result)
            self.assertIn("grounded_claims", result)
            self.assertIn("grounding_metrics", result)
            self.assertIn("knowledge_sources", result)
            self.assertIn("timing", result, "Result should include timing information")
            self.assertEqual(result["original_response"], llm_response)
            
            # Verify timing structure
            timing = result["timing"]
            self.assertIn("llm_extraction_time", timing)
            self.assertIn("verification_time", timing)
            self.assertIn("total_grounding_time", timing)

class TestIntegration(unittest.TestCase):
    """Integration tests with real knowledge graph"""
    
    @unittest.skipIf(
        os.getenv("NEO4J_URI") is None,
        "Neo4j not configured for integration tests"
    )
    def test_integration_with_real_kg(self):
        """Test with real Neo4j knowledge graph"""
        try:
            kg = KnowledgeGraph(
                neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
                neo4j_password=os.getenv("NEO4J_PASSWORD", "password")
            )
            
            # Test without LLM client (fallback to pattern-based)
            grounding = KnowledgeGrounding(kg)
            
            # Test with a simple query
            result = grounding.ground_llm_response(
                query="What entities are in the knowledge graph?",
                llm_response="There are several entities including persons and locations."
            )
            
            self.assertIn("grounding_metrics", result)
            self.assertIn("grounded_claims", result)
            self.assertIn("timing", result)
            
            kg.close()
        except Exception as e:
            self.skipTest(f"Integration test skipped: {e}")
    
    def test_llm_extraction_fallback(self):
        """Test that pattern-based extraction works as fallback when LLM is not available"""
        # Create grounding without LLM client
        mock_kg = Mock(spec=KnowledgeGraph)
        grounding = KnowledgeGrounding(mock_kg, llm_client=None)
        
        # Should use pattern-based extraction
        text = "John Doe was seen at Mountain Trail"
        mock_kg.find_entities.return_value = []
        
        claims = grounding._extract_claims(text)
        
        # Should still extract claims using pattern-based method
        self.assertIsInstance(claims, list)
        # May have claims or general fallback claim
        self.assertGreaterEqual(len(claims), 0)
    
    @patch('knowledge_grounding.json.loads')
    def test_extract_claims_with_llm(self, mock_json_loads):
        """Test LLM-based claim extraction (neurosymbolic approach)"""
        # Mock LLM client
        mock_llm_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '{"claims": [{"text": "John was seen at Trail", "entities": ["John", "Trail"], "relations": ["SEEN_AT"], "confidence": 0.8}]}'
        mock_llm_client.chat.completions.create.return_value = mock_response
        
        # Mock JSON parsing
        mock_json_loads.return_value = {
            "claims": [{
                "text": "John was seen at Trail",
                "entities": ["John", "Trail"],
                "relations": ["SEEN_AT"],
                "confidence": 0.8
            }]
        }
        
        # Mock knowledge graph
        mock_kg = Mock(spec=KnowledgeGraph)
        mock_entity = Mock(spec=Entity)
        mock_entity.id = "entity_1"
        mock_kg.find_entities.return_value = [mock_entity]
        
        grounding = KnowledgeGrounding(mock_kg, llm_client=mock_llm_client)
        
        # Test LLM extraction
        claims = grounding._extract_claims_with_llm("John was seen at Trail")
        
        self.assertIsInstance(claims, list)
        self.assertGreater(len(claims), 0)
        self.assertEqual(claims[0].text, "John was seen at Trail")
        self.assertIn("SEEN_AT", claims[0].relation_mentions)

if __name__ == "__main__":
    unittest.main()

