#!/usr/bin/env python3
"""
Knowledge Grounding Framework for ClueMeister Agent
Provides mechanisms to ground LLM responses in the knowledge graph
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from knowledge_graph import KnowledgeGraph, Entity, Relation, EntityType, RelationType
import re
import logging
import json
import time

logger = logging.getLogger(__name__)

@dataclass
class Claim:
    """A claim extracted from LLM response"""
    text: str
    entity_mentions: List[str]  # Entity IDs mentioned
    relation_mentions: List[str]  # Relation types mentioned
    confidence: float
    source: str  # "llm" or "kg"

@dataclass
class Evidence:
    """Evidence supporting a claim"""
    claim: Claim
    supporting_entities: List[Entity]
    supporting_relations: List[Relation]
    confidence: float
    reasoning_path: List[str]  # Path in knowledge graph

class KnowledgeGrounding:
    """Knowledge Grounding System"""
    
    def __init__(self, knowledge_graph: KnowledgeGraph, llm_client: Optional[Any] = None, llm_type: str = "openai"):
        """
        Initialize knowledge grounding system
        
        Args:
            knowledge_graph: Knowledge graph instance
            llm_client: Optional LLM client (OpenAI client or Gemini model) for neurosymbolic claim extraction
            llm_type: Type of LLM client ("openai" or "gemini")
        """
        self.kg = knowledge_graph
        self.llm_client = llm_client
        self.llm_type = llm_type
        self.entity_patterns = self._build_entity_patterns()
    
    def ground_llm_response(self, query: str, llm_response: str, 
                          context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Ground an LLM response in the knowledge graph
        
        Args:
            query: Original query
            llm_response: LLM-generated response
            context: Additional context (e.g., mission data)
        
        Returns:
            Grounded response with evidence and confidence
        """
        
        # Step 1: Extract claims from LLM response (with timing)
        extraction_start = time.time()
        claims = self._extract_claims(llm_response, context)
        extraction_time = time.time() - extraction_start
        
        # Step 2: Ground each claim in knowledge graph (with timing)
        verification_start = time.time()
        grounded_claims = []
        for claim in claims:
            grounded = self._ground_claim(claim)
            grounded_claims.append(grounded)
        verification_time = time.time() - verification_start
        
        # Step 3: Calculate overall grounding metrics
        metrics = self._calculate_grounding_metrics(grounded_claims)
        
        # Step 4: Generate grounded response with timing information
        total_grounding_time = extraction_time + verification_time
        grounded_response = {
            "original_response": llm_response,
            "grounded_claims": grounded_claims,
            "grounding_metrics": metrics,
            "knowledge_sources": self._extract_knowledge_sources(grounded_claims),
            "confidence": metrics["overall_confidence"],
            "timing": {
                "llm_extraction_time": extraction_time,
                "verification_time": verification_time,
                "total_grounding_time": total_grounding_time,
                "note": "Does not include initial LLM response generation time"
            }
        }
        
        return grounded_response
    
    def _extract_claims(self, text: str, context: Dict = None) -> List[Claim]:
        """
        Extract claims from LLM response
        
        Uses LLM structured output if available (neurosymbolic approach),
        falls back to pattern-based extraction if LLM is not available.
        """
        # Try LLM extraction first (neurosymbolic approach)
        if self.llm_client:
            try:
                claims = self._extract_claims_with_llm(text, context)
                if claims:
                    logger.debug(f"Extracted {len(claims)} claims using LLM")
                    return claims
            except Exception as e:
                logger.warning(f"LLM claim extraction failed, falling back to pattern-based: {e}")
        
        # Fallback to pattern-based extraction
        return self._extract_claims_pattern_based(text, context)
    
    def _extract_claims_with_llm(self, text: str, context: Dict = None) -> List[Claim]:
        """
        Extract claims using LLM structured output (Neurosymbolic approach)
        
        This is the true neurosymbolic method: using neural network (LLM) 
        to extract semantic claims, then grounding them in symbolic knowledge graph.
        Supports both OpenAI and Gemini APIs.
        """
        if not self.llm_client:
            raise ValueError("LLM client not available")
        
        # Create prompt for structured claim extraction
        system_message = """You are an expert at extracting factual claims from text.
        Extract all factual claims that mention entities (people, locations, objects) 
        and relations between them. Return the result as JSON."""
        
        prompt = f"""Extract factual claims from the following text. 
For each claim, identify:
- The claim text (exact phrase from the text)
- Entities mentioned (person names, locations, objects, clues, etc.)
- Relations mentioned (seen_at, found_in, located_in, last_seen, etc.)
- Your confidence in this claim (0.0 to 1.0)

Text to analyze:
{text}

Return JSON format with this exact structure:
{{
  "claims": [
    {{
      "text": "exact claim text from the input",
      "entities": ["entity1", "entity2"],
      "relations": ["relation_type"],
      "confidence": 0.7
    }}
  ]
}}

Only extract claims that mention specific entities or relations. 
Do not extract general statements without specific entities.
Return valid JSON only, no additional text."""

        try:
            if self.llm_type == "gemini":
                # Use Gemini API
                full_prompt = f"System: {system_message}\n\nUser: {prompt}"
                response = self.llm_client.generate_content(
                    full_prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 2000,
                    }
                )
                response_text = response.text
            else:
                # Use OpenAI API
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ]
                response = self.llm_client.chat.completions.create(
                    model="gpt-4",
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
                response_text = response.choices[0].message.content
            
            # Parse JSON response
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response if wrapped in markdown
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    raise ValueError("Could not parse JSON from LLM response")
            
            # Convert to Claim objects
            claims = []
            for claim_data in result.get("claims", []):
                claim_text = claim_data.get("text", "")
                entities = claim_data.get("entities", [])
                relations = claim_data.get("relations", [])
                confidence = float(claim_data.get("confidence", 0.5))
                
                # Find entity IDs in knowledge graph
                entity_ids = []
                for entity_name in entities:
                    found_entities = self.kg.find_entities(properties={"name": entity_name})
                    if found_entities:
                        entity_ids.extend([e.id for e in found_entities])
                
                claims.append(Claim(
                    text=claim_text,
                    entity_mentions=entity_ids,
                    relation_mentions=relations,
                    confidence=confidence,
                    source="llm_extracted"
                ))
            
            return claims
            
        except Exception as e:
            logger.error(f"Error in LLM claim extraction: {e}")
            raise
    
    def _extract_claims_pattern_based(self, text: str, context: Dict = None) -> List[Claim]:
        """Extract claims using pattern-based matching (fallback method)"""
        
        claims = []
        
        # Simple pattern-based extraction (can be enhanced with NER)
        # Look for statements about entities and relations
        
        # Pattern 1: "Person X was seen at Location Y"
        seen_pattern = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:was|is)\s+seen\s+at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
        matches = re.finditer(seen_pattern, text, re.IGNORECASE)
        for match in matches:
            person_name = match.group(1)
            location_name = match.group(2)
            
            # Find entities in knowledge graph
            person_entities = self.kg.find_entities(
                entity_type=EntityType.PERSON,
                properties={"name": person_name}
            )
            location_entities = self.kg.find_entities(
                entity_type=EntityType.LOCATION,
                properties={"name": location_name}
            )
            
            if person_entities and location_entities:
                claims.append(Claim(
                    text=match.group(0),
                    entity_mentions=[e.id for e in person_entities + location_entities],
                    relation_mentions=["SEEN_AT"],
                    confidence=0.7,
                    source="llm"
                ))
        
        # Pattern 2: "High priority area: X"
        priority_pattern = r"(?:high|medium|low)\s+priority\s+(?:area|location|region):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
        matches = re.finditer(priority_pattern, text, re.IGNORECASE)
        for match in matches:
            area_name = match.group(1)
            area_entities = self.kg.find_entities(
                entity_type=EntityType.AREA,
                properties={"name": area_name}
            )
            
            if area_entities:
                claims.append(Claim(
                    text=match.group(0),
                    entity_mentions=[e.id for e in area_entities],
                    relation_mentions=[],
                    confidence=0.6,
                    source="llm"
                ))
        
        # Pattern 3: Extract entity names (capitalized words that might be entities)
        entity_name_pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
        entity_matches = re.finditer(entity_name_pattern, text)
        entity_names = set()
        for match in entity_matches:
            name = match.group(1)
            # Skip common words
            if name.lower() not in ["the", "and", "or", "but", "for", "with", "from", "that", "this"]:
                entity_names.add(name)
        
        # Check if these names exist in knowledge graph
        for name in list(entity_names)[:10]:  # Limit to first 10
            entities = self.kg.find_entities(properties={"name": name})
            if entities:
                claims.append(Claim(
                    text=f"Entity mentioned: {name}",
                    entity_mentions=[e.id for e in entities],
                    relation_mentions=[],
                    confidence=0.5,
                    source="llm"
                ))
        
        # If no patterns matched, create a general claim
        if not claims:
            claims.append(Claim(
                text=text[:200],  # First 200 chars
                entity_mentions=[],
                relation_mentions=[],
                confidence=0.5,
                source="llm"
            ))
        
        return claims
    
    def _is_properly_grounded(self, confidence: float,
                             entities: List[Entity],
                             relations: List[Relation],
                             path: List[str]) -> bool:
        """
        Check if claim is properly grounded with strict criteria
        
        Requirements:
        1. Confidence >= 0.5
        2. Must have at least one Relation or Reasoning Path
        3. Must have at least one entity match
        """
        # Requirement 1: Confidence threshold
        if confidence < 0.5:
            return False
        
        # Requirement 2: Must have at least one Relation or Reasoning Path
        has_relation = len(relations) > 0
        has_path = path and len(path) >= 2
        
        if not (has_relation or has_path):
            return False
        
        # Requirement 3: Must have at least one entity match
        if len(entities) == 0:
            return False
        
        return True
    
    def _ground_claim(self, claim: Claim) -> Dict[str, Any]:
        """Ground a single claim in the knowledge graph"""
        
        # Find supporting evidence
        supporting_entities = []
        supporting_relations = []
        
        # Search for entities mentioned in the claim by ID
        for entity_id in claim.entity_mentions:
            entities = self.kg.find_entities(properties={"id": entity_id})
            if entities:
                supporting_entities.extend(entities)
        
        # Always try to find entities by name from text (even if entity_mentions exist)
        if claim.text:
            # Extract potential entity names from text
            entity_names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", claim.text)
            found_entity_ids = set(claim.entity_mentions)
            
            for name in entity_names[:10]:  # Limit to first 10
                # Try exact match first
                entities = self.kg.find_entities(properties={"name": name})
                if not entities:
                    # Try partial match - get all entities and check if name contains or is contained
                    all_entities = self.kg.find_entities()
                    for entity in all_entities:
                        if name.lower() in entity.name.lower() or entity.name.lower() in name.lower():
                            if entity.id not in found_entity_ids:
                                entities = [entity]
                                break
                
                if entities:
                    for entity in entities:
                        if entity.id not in found_entity_ids:
                            supporting_entities.append(entity)
                            found_entity_ids.add(entity.id)
                            # Update claim with found entity IDs
                            if entity.id not in claim.entity_mentions:
                                claim.entity_mentions.append(entity.id)
        
        # Search for relations mentioned in the claim
        for rel_type_str in claim.relation_mentions:
            try:
                rel_type = RelationType[rel_type_str]
                relations = self.kg.find_relations(relation_type=rel_type)
                supporting_relations.extend(relations)
            except KeyError:
                pass
        
        # Also search for relations connected to found entities
        if supporting_entities:
            for entity in supporting_entities[:3]:  # Limit to avoid too many queries
                neighbors = self.kg.get_entity_neighbors(entity.id)
                for neighbor_entity, relation in neighbors:
                    if relation not in supporting_relations:
                        supporting_relations.append(relation)
        
        # Find reasoning path if entities are connected
        reasoning_path = []
        if len(claim.entity_mentions) >= 2:
            try:
                paths = self.kg.find_paths(
                    source_entity=claim.entity_mentions[0],
                    target_entity=claim.entity_mentions[1],
                    max_length=3
                )
                if paths:
                    reasoning_path = paths[0]
            except Exception as e:
                logger.debug(f"Failed to find path: {e}")
        
        # Calculate grounding confidence
        confidence = self._calculate_grounding_confidence(
            claim, supporting_entities, supporting_relations, reasoning_path
        )
        
        # Use strict grounding criteria
        is_grounded = self._is_properly_grounded(
            confidence, supporting_entities, supporting_relations, reasoning_path
        )
        
        return {
            "claim": {
                "text": claim.text,
                "entity_mentions": claim.entity_mentions,
                "relation_mentions": claim.relation_mentions,
                "confidence": claim.confidence,
                "source": claim.source
            },
            "supporting_entities": [self._entity_to_dict(e) for e in supporting_entities],
            "supporting_relations": [self._relation_to_dict(r) for r in supporting_relations],
            "reasoning_path": reasoning_path,
            "grounding_confidence": confidence,
            "is_grounded": is_grounded  # Strict criteria: >=0.5 confidence + relation/path required
        }
    
    def _calculate_grounding_confidence(self, claim: Claim, 
                                       entities: List[Entity],
                                       relations: List[Relation],
                                       path: List[str]) -> float:
        """
        Calculate confidence that claim is grounded in KG
        
        Scoring ensures that only claims with Relations or Paths can reach 0.5+ threshold.
        """
        
        confidence = 0.0
        
        # Base confidence from entity matches
        # Limited to 0.4 max to ensure Relation/Path is required for 0.5+ threshold
        if entities:
            entity_score = min(0.4, 0.2 + 0.1 * min(len(entities), 2))
            confidence += entity_score
        
        # Boost from relation matches (required for proper grounding)
        if relations:
            # 0.25 for 1 relation, 0.35 for 2+, up to 0.45
            relation_score = min(0.45, 0.2 + 0.15 * min(len(relations), 2))
            confidence += relation_score
        
        # Boost from reasoning path (strongest signal, also required)
        if path and len(path) >= 2:
            confidence += 0.35  # Strong signal for proper grounding
        
        # Bonus for having both entities and relations
        if entities and relations:
            confidence += 0.1
        
        # If only entities (no relations or path), cap at 0.4
        # This ensures proper grounding requires relation or path
        if entities and not relations and not (path and len(path) >= 2):
            confidence = min(confidence, 0.4)
        
        # Ensure minimum confidence if we have any evidence
        if entities or relations:
            confidence = max(confidence, 0.1)  # Minimum 0.1 if any evidence exists
        
        return min(1.0, confidence)
    
    def _calculate_grounding_metrics(self, grounded_claims: List[Dict]) -> Dict[str, Any]:
        """Calculate overall grounding metrics"""
        
        if not grounded_claims:
            return {
                "overall_confidence": 0.0,
                "grounding_rate": 0.0,
                "average_confidence": 0.0,
                "total_claims": 0,
                "grounded_claims": 0
            }
        
        grounded_count = sum(1 for c in grounded_claims if c["is_grounded"])
        total_confidence = sum(c["grounding_confidence"] for c in grounded_claims)
        
        return {
            "overall_confidence": total_confidence / len(grounded_claims),
            "grounding_rate": grounded_count / len(grounded_claims),
            "average_confidence": total_confidence / len(grounded_claims),
            "total_claims": len(grounded_claims),
            "grounded_claims": grounded_count
        }
    
    def _extract_knowledge_sources(self, grounded_claims: List[Dict]) -> List[str]:
        """Extract unique knowledge sources"""
        
        sources = set()
        
        for claim_data in grounded_claims:
            for entity in claim_data["supporting_entities"]:
                sources.add(entity.get("source", "unknown"))
            for relation in claim_data["supporting_relations"]:
                sources.add(relation.get("source", "unknown"))
        
        return list(sources)
    
    def _entity_to_dict(self, entity: Entity) -> Dict:
        """Convert Entity to dictionary"""
        return {
            "id": entity.id,
            "type": entity.type.value,
            "name": entity.name,
            "properties": entity.properties,
            "confidence": entity.confidence,
            "source": entity.source
        }
    
    def _relation_to_dict(self, relation: Relation) -> Dict:
        """Convert Relation to dictionary"""
        return {
            "id": relation.id,
            "type": relation.type.value,
            "source_entity": relation.source_entity,
            "target_entity": relation.target_entity,
            "properties": relation.properties,
            "confidence": relation.confidence,
            "source": relation.source
        }
    
    def _build_entity_patterns(self) -> Dict:
        """Build patterns for entity extraction"""
        # Can be enhanced with more sophisticated NLP
        return {}

