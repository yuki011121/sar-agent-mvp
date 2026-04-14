#!/usr/bin/env python3
"""
ClueMeister Agent - Intelligent Analysis Center for Search and Rescue Operations
Integrates information from all agents and uses knowledge graphs to discover clue correlations
"""

import os
import time
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from dataclasses import asdict
from dotenv import load_dotenv

from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder, 
    EntityType, RelationType, Entity, Relation
)

from knowledge_grounding import KnowledgeGrounding

from shared import RedisBus, wrap_envelope, parse_message_from_stream

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 10))
AGENT_NAME = "cluemeister-agent"
AGENT_VERSION = "cluemeister-agent-v1.0"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Neo4j configuration (required)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Visualization configuration
EXPORT_VISUALIZATIONS = os.getenv("EXPORT_VISUALIZATIONS", "true").lower() == "true"
VISUALIZATION_OUTPUT_DIR = os.getenv("VISUALIZATION_OUTPUT_DIR", "/workspace/visualizations")

INPUT_STREAMS = [
    "photo.analysis.raw",
    "interview.analysis.raw", 
    "history.out.raw",
    "weather.forecast.raw",
    "path.analysis.raw",
    "health.assessment.raw",
    "logistics.requests.raw"
]

OUTPUT_STREAM = "cluemeister.analysis.raw"
DEAD_LETTER_STREAM = "system.dead_letter"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(AGENT_NAME)

class ClueMeisterAgent:
    """ClueMeister Intelligent Analysis Agent"""
    
    def __init__(self):
        self.name = AGENT_NAME
        self.version = AGENT_VERSION
        self.google_api_key = GOOGLE_API_KEY
        
        # Initialize knowledge graph (Neo4j required)
        self.knowledge_graph = KnowledgeGraph(
            neo4j_uri=NEO4J_URI,
            neo4j_user=NEO4J_USER,
            neo4j_password=NEO4J_PASSWORD
        )
        self.graph_builder = ClueMeisterGraphBuilder(self.knowledge_graph)
        
        # Initialize Gemini client (needed for knowledge grounding)
        if self.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.google_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("Gemini client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.gemini_model = None
        else:
            logger.warning("No Google API key found. Using fallback analysis.")
            self.gemini_model = None
        
        # Initialize knowledge grounding system with LLM client (for neurosymbolic extraction)
        self.knowledge_grounding = KnowledgeGrounding(
            self.knowledge_graph, 
            llm_client=self.gemini_model,
            llm_type="gemini"
        )
        logger.info("Knowledge grounding system initialized with Gemini for neurosymbolic extraction")
        
        # Create visualization output directory if needed
        if EXPORT_VISUALIZATIONS:
            os.makedirs(VISUALIZATION_OUTPUT_DIR, exist_ok=True)
        
        # Data cache
        self.recent_data = {}
        self.analysis_history = []
        
        logger.info(f"ClueMeister Agent initialized with knowledge graph")
    
    def ask_llm(self, prompt: str, system_message: str = None) -> Optional[str]:
        """Call LLM for analysis using Gemini"""
        if not self.gemini_model:
            logger.warning("No Gemini client available. Using fallback.")
            return None
        
        try:
            # Combine system message and prompt for Gemini
            full_prompt = ""
            if system_message:
                full_prompt = f"System: {system_message}\n\nUser: {prompt}"
            else:
                full_prompt = prompt
            
            response = self.gemini_model.generate_content(
                full_prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 1000,
                }
            )
            return response.text
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None
    
    def ask_llm_with_grounding(self, prompt: str, system_message: str = None, 
                              context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Ask LLM with knowledge grounding
        
        Args:
            prompt: Query prompt
            system_message: Optional system message
            context: Additional context for grounding
        
        Returns:
            Dictionary with grounded response and metrics, including detailed timing breakdown
        """
        import time
        
        # Stage 1: Initial LLM response generation
        llm_start = time.time()
        llm_response = self.ask_llm(prompt, system_message)
        initial_llm_time = time.time() - llm_start
        
        if not llm_response:
            return {
                "error": "LLM response failed",
                "original_response": None,
                "grounding_metrics": {
                    "overall_confidence": 0.0,
                    "grounding_rate": 0.0,
                    "total_claims": 0,
                    "grounded_claims": 0
                },
                "timing": {
                    "initial_llm_time": initial_llm_time,
                    "end_to_end_time": initial_llm_time,
                    "note": "LLM response generation failed"
                }
            }
        
        # Stage 2: Knowledge grounding (includes LLM extraction and verification)
        grounded = self.knowledge_grounding.ground_llm_response(
            query=prompt,
            llm_response=llm_response,
            context=context
        )
        
        # Merge timing information for complete end-to-end tracking
        if "timing" in grounded:
            grounded["timing"]["initial_llm_time"] = initial_llm_time
            grounded["timing"]["end_to_end_time"] = (
                initial_llm_time + grounded["timing"]["total_grounding_time"]
            )
            grounded["timing"]["breakdown"] = {
                "stage1_initial_llm": initial_llm_time,
                "stage2_llm_extraction": grounded["timing"]["llm_extraction_time"],
                "stage3_verification": grounded["timing"]["verification_time"],
                "total": grounded["timing"]["end_to_end_time"]
            }
        else:
            # Fallback if timing not available
            grounded["timing"] = {
                "initial_llm_time": initial_llm_time,
                "end_to_end_time": initial_llm_time,
                "note": "Timing breakdown not available"
            }
        
        return grounded
    
    def process_photo_analysis(self, photo_data: Dict[str, Any]) -> List[str]:
        """Process photo analysis data"""
        try:
            logger.info("Processing photo analysis data")
            
            # Add photo analysis entity
            photo_entity_id = self.graph_builder.add_photo_analysis(photo_data)
            entity_ids = [photo_entity_id]
            
            # Process detected persons
            detections = photo_data.get("detections", [])
            person_analysis = photo_data.get("person_analysis", {})
            
            for detection in detections:
                if detection.get("class") == "person":
                    # Create detected person entity
                    person_id = self.graph_builder._generate_id("detected_person")
                    person_entity = Entity(
                        id=person_id,
                        type=EntityType.PERSON,
                        name="Detected Person",
                        properties={
                            "detection_confidence": detection.get("confidence"),
                            "bbox": detection.get("bbox"),
                            "hair_color": detection.get("hair_color", "unknown"),
                            "clothing_color": detection.get("clothing_color", "unknown"),
                            "gender": detection.get("gender", "unknown"),
                            "person_id": detection.get("person_id")
                        },
                        confidence=detection.get("confidence", 0.5),
                        source="photo_analysis"
                    )
                    self.knowledge_graph.add_entity(person_entity)
                    entity_ids.append(person_id)
                    
                    # Link to photo
                    self.graph_builder.link_entities(
                        photo_entity_id, person_id,
                        RelationType.FOUND_IN,
                        {"detection_method": "yolo", "bbox": detection.get("bbox")},
                        confidence=detection.get("confidence", 0.5),
                        source="photo_analysis"
                    )
            
            # Process SAR context
            sar_context = photo_data.get("sar_context", {})
            if sar_context:
                # Add search area entity
                if sar_context.get("search_priority"):
                    area_id = self.graph_builder._generate_id("search_area")
                    area_entity = Entity(
                        id=area_id,
                        type=EntityType.AREA,
                        name=f"Search Area: {photo_data.get('filename', 'unknown')}",
                        properties={
                            "priority": sar_context.get("search_priority"),
                            "urgency": sar_context.get("urgency_level"),
                            "accessibility": sar_context.get("accessibility", {}),
                            "people_count": person_analysis.get("total_people", 0),
                            "equipment_count": len(sar_context.get("emergency_equipment", []))
                        },
                        confidence=0.8,
                        source="photo_analysis"
                    )
                    self.knowledge_graph.add_entity(area_entity)
                    entity_ids.append(area_id)
                    
                    # Link to photo
                    self.graph_builder.link_entities(
                        photo_entity_id, area_id,
                        RelationType.LOCATED_IN,
                        {"analysis_type": "sar_context"},
                        confidence=0.8,
                        source="photo_analysis"
                    )
            
            logger.info(f"Processed photo analysis: {len(entity_ids)} entities created")
            return entity_ids
            
        except Exception as e:
            logger.error(f"Error processing photo analysis: {e}")
            return []
    
    def process_interview_analysis(self, interview_data: Dict[str, Any]) -> List[str]:
        """Process interview analysis data"""
        try:
            logger.info("Processing interview analysis data")
            
            analysis = interview_data.get("analysis", {})
            entity_ids = []
            
            # Process important sections
            important_sections = analysis.get("important_sections", [])
            for section in important_sections:
                # Create clue entity
                clue_id = self.graph_builder._generate_id("interview_clue")
                clue_entity = Entity(
                    id=clue_id,
                    type=EntityType.CLUE,
                    name=f"Interview Clue: {section.get('importance_score', 0)}/10",
                    properties={
                        "section": section.get("section", ""),
                        "importance_score": section.get("importance_score", 0),
                        "reason": section.get("reason", ""),
                        "source_type": "interview"
                    },
                    confidence=min(section.get("importance_score", 0) / 10.0, 1.0),
                    source="interview_analysis"
                )
                self.knowledge_graph.add_entity(clue_entity)
                entity_ids.append(clue_id)
            
            # Process entity extraction
            entity_extraction = analysis.get("entity_extraction", [])
            for extraction in entity_extraction:
                entities = extraction.get("entities", {})
                
                # Process people
                for person in entities.get("people", []):
                    person_id = self.graph_builder._generate_id("mentioned_person")
                    person_entity = Entity(
                        id=person_id,
                        type=EntityType.PERSON,
                        name=person,
                        properties={
                            "mentioned_in": extraction.get("section", ""),
                            "source_type": "interview_mention"
                        },
                        confidence=0.7,
                        source="interview_analysis"
                    )
                    self.knowledge_graph.add_entity(person_entity)
                    entity_ids.append(person_id)
                
                # Process locations
                for place in entities.get("places", []):
                    location_id = self.graph_builder._generate_id("mentioned_location")
                    location_entity = Entity(
                        id=location_id,
                        type=EntityType.LOCATION,
                        name=place,
                        properties={
                            "mentioned_in": extraction.get("section", ""),
                            "source_type": "interview_mention"
                        },
                        confidence=0.7,
                        source="interview_analysis"
                    )
                    self.knowledge_graph.add_entity(location_entity)
                    entity_ids.append(location_id)
                
                # Process times
                for time_ref in entities.get("times", []):
                    time_id = self.graph_builder._generate_id("mentioned_time")
                    time_entity = Entity(
                        id=time_id,
                        type=EntityType.TIME,
                        name=time_ref,
                        properties={
                            "mentioned_in": extraction.get("section", ""),
                            "source_type": "interview_mention"
                        },
                        confidence=0.7,
                        source="interview_analysis"
                    )
                    self.knowledge_graph.add_entity(time_entity)
                    entity_ids.append(time_id)
            
            # Process high confidence sections
            high_confidence = analysis.get("high_confidence_sections", [])
            for section in high_confidence:
                # Create high confidence clue
                clue_id = self.graph_builder._generate_id("high_confidence_clue")
                clue_entity = Entity(
                    id=clue_id,
                    type=EntityType.CLUE,
                    name="High Confidence Interview Clue",
                    properties={
                        "section": section.get("section", ""),
                        "confidence_score": section.get("confidence_score", 0),
                        "confidence_level": section.get("confidence_level", "unknown"),
                        "source_type": "high_confidence_interview"
                    },
                    confidence=section.get("confidence_score", 0) / 10.0,
                    source="interview_analysis"
                )
                self.knowledge_graph.add_entity(clue_entity)
                entity_ids.append(clue_id)
            
            logger.info(f"Processed interview analysis: {len(entity_ids)} entities created")
            return entity_ids
            
        except Exception as e:
            logger.error(f"Error processing interview analysis: {e}")
            return []
    
    def process_history_analysis(self, history_data: Dict[str, Any]) -> List[str]:
        """Process history analysis data - convert to structured knowledge graph"""
        try:
            logger.info("Processing history analysis data")
            
            entity_ids = []
            
            # Extract summary and actions (from LLM output)
            summary = history_data.get("summary", "")
            actions = history_data.get("actions", "")
            
            # Extract matched cases if available (from history agent)
            matched_cases = history_data.get("matched_cases", [])
            query_case = history_data.get("query_case", {})  # Current case being analyzed
            
            # Create a historical case entity for the summary
            if summary or actions:
                case_id = self.graph_builder._generate_id("historical_case")
                case_entity = Entity(
                    id=case_id,
                    type=EntityType.EVENT,
                    name="Historical SAR Case Analysis",
                    properties={
                        "summary": summary,
                        "actions": actions,
                        "source_type": "historical_analysis",
                        "matched_cases_count": len(matched_cases)
                    },
                    confidence=0.8,
                    source="history_agent"
                )
                self.knowledge_graph.add_entity(case_entity)
                entity_ids.append(case_id)
                
                # Link to current case if query_case has an ID
                current_case_id = query_case.get("case_id")
                if current_case_id:
                    self.graph_builder.link_entities(
                        current_case_id, case_id,
                        RelationType.SIMILAR_TO,
                        {"relation": "historical_analysis"},
                        confidence=0.8,
                        source="history_agent"
                    )
            
            # Process each matched historical case (if provided)
            person_id = None
            location_id = None
            
            for idx, case in enumerate(matched_cases):
                person_id = None
                location_id = None
                
                # Create person entity from historical case
                if case.get("Age") or case.get("Sex") or case.get("Subject_Category"):
                    person_id = self.graph_builder._generate_id("historical_person")
                    person_entity = Entity(
                        id=person_id,
                        type=EntityType.PERSON,
                        name=f"Historical Person {idx+1}",
                        properties={
                            "age": case.get("Age"),
                            "gender": case.get("Sex", "").upper() if case.get("Sex") else None,
                            "category": case.get("Subject_Category"),
                            "status": case.get("Subject_Status"),
                            "source_type": "historical_case",
                            "case_index": idx
                        },
                        confidence=0.7,
                        source="history_agent"
                    )
                    self.knowledge_graph.add_entity(person_entity)
                    entity_ids.append(person_id)
                
                # Create location/terrain entity
                if case.get("Terrain") or case.get("Data_Source"):
                    location_id = self.graph_builder._generate_id("historical_location")
                    location_entity = Entity(
                        id=location_id,
                        type=EntityType.LOCATION,
                        name=f"{case.get('Data_Source', 'Unknown')} - {case.get('Terrain', 'Unknown')}",
                        properties={
                            "terrain_type": case.get("Terrain"),
                            "data_source": case.get("Data_Source"),
                            "source_type": "historical_case",
                            "case_index": idx
                        },
                        confidence=0.7,
                        source="history_agent"
                    )
                    self.knowledge_graph.add_entity(location_entity)
                    entity_ids.append(location_id)
                
                # Create historical case event
                hist_case_id = self.graph_builder._generate_id("historical_case_event")
                hist_case_entity = Entity(
                    id=hist_case_id,
                    type=EntityType.EVENT,
                    name=f"Historical Case {idx+1}: {case.get('Incident_Outcome', 'Unknown')}",
                    properties={
                        "outcome": case.get("Incident_Outcome"),
                        "terrain": case.get("Terrain"),
                        "activity": case.get("Subject_Activity"),
                        "category": case.get("Subject_Category"),
                        "source_type": "historical_case",
                        "case_index": idx
                    },
                    confidence=0.8,
                    source="history_agent"
                )
                self.knowledge_graph.add_entity(hist_case_entity)
                entity_ids.append(hist_case_id)
                
                # Create relationships (use CONNECTED_TO if EXPERIENCED/OCCURRED_AT don't exist)
                if person_id:
                    # Use CONNECTED_TO as a generic relation
                    self.graph_builder.link_entities(
                        person_id, hist_case_id,
                        RelationType.CONNECTED_TO,
                        {"case_type": "historical", "relation": "experienced"},
                        confidence=0.8,
                        source="history_agent"
                    )
                
                if location_id:
                    # Use LOCATED_IN as relation
                    self.graph_builder.link_entities(
                        hist_case_id, location_id,
                        RelationType.LOCATED_IN,
                        {"terrain": case.get("Terrain"), "relation": "occurred_at"},
                        confidence=0.8,
                        source="history_agent"
                    )
                
                # Link to current case if available
                if current_case_id:
                    self.graph_builder.link_entities(
                        current_case_id, hist_case_id,
                        RelationType.SIMILAR_TO,
                        {"similarity_source": "history_agent", "case_index": idx},
                        confidence=0.75,
                        source="history_agent"
                    )
            
            logger.info(f"Processed history analysis: {len(entity_ids)} entities created")
            return entity_ids
            
        except Exception as e:
            logger.error(f"Error processing history analysis: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def process_weather_data(self, weather_data: Dict[str, Any]) -> List[str]:
        """Process weather data"""
        try:
            logger.info("Processing weather data")
            
            # Add weather entity
            weather_id = self.graph_builder.add_weather_condition(weather_data)
            
            logger.info(f"Processed weather data: 1 entity created")
            return [weather_id]
            
        except Exception as e:
            logger.error(f"Error processing weather data: {e}")
            return []

    def process_health_assessment(self, health_data: Dict[str, Any]) -> List[str]:
        """Process health assessment data into KG entities and relations"""
        try:
            logger.info("Processing health assessment data")

            entity_ids: List[str] = []

            # Create health assessment event
            assessment = health_data.get("assessment", {})
            recommended_actions = assessment.get("recommended_actions") or health_data.get("recommended_actions", [])
            required_supplies = assessment.get("required_supplies") or health_data.get("required_supplies", [])

            health_event_id = self.graph_builder._generate_id("health_assessment")
            health_event = Entity(
                id=health_event_id,
                type=EntityType.EVENT,
                name="Health Assessment",
                properties={
                    "risk_level": assessment.get("risk_level") or health_data.get("risk_level"),
                    "primary_health_risks": assessment.get("primary_health_risks", []),
                    "recommended_actions": recommended_actions,
                },
                confidence=0.8,
                source="health_assessment"
            )
            self.knowledge_graph.add_entity(health_event)
            entity_ids.append(health_event_id)

            # Create resource entities and link
            for supply in required_supplies:
                item_name = supply.get("item") or supply.get("name")
                if not item_name:
                    continue
                resource_id = self.graph_builder._generate_id("resource")
                resource_entity = Entity(
                    id=resource_id,
                    type=EntityType.RESOURCE,
                    name=item_name,
                    properties={
                        "quantity": supply.get("quantity"),
                        "priority": supply.get("priority"),
                    },
                    confidence=0.9,
                    source="health_assessment"
                )
                self.knowledge_graph.add_entity(resource_entity)
                entity_ids.append(resource_id)
                self.graph_builder.link_entities(
                    health_event_id,
                    resource_id,
                    RelationType.REQUIRES,
                    {"reason": "required_supply_from_health_assessment"},
                    confidence=0.9,
                    source="health_assessment",
                )

            logger.info(f"Processed health assessment: {len(entity_ids)} entities created")
            return entity_ids
        except Exception as e:
            logger.error(f"Error processing health assessment: {e}")
            return []

    def process_logistics_request(self, logistics_data: Dict[str, Any]) -> List[str]:
        """Process logistics request data into KG entities and relations"""
        try:
            logger.info("Processing logistics request data")

            entity_ids: List[str] = []

            priority = logistics_data.get("priority") or logistics_data.get("metadata", {}).get("priority")
            supplies = logistics_data.get("supplies_needed") or logistics_data.get("supplies") or []

            request_id = self.graph_builder._generate_id("logistics_request")
            request_entity = Entity(
                id=request_id,
                type=EntityType.EVENT,
                name="Logistics Request",
                properties={
                    "priority": priority,
                },
                confidence=0.8,
                source="logistics_request"
            )
            self.knowledge_graph.add_entity(request_entity)
            entity_ids.append(request_id)

            for supply in supplies:
                item_name = supply.get("item") or supply.get("name")
                if not item_name:
                    continue
                resource_id = self.graph_builder._generate_id("resource")
                resource_entity = Entity(
                    id=resource_id,
                    type=EntityType.RESOURCE,
                    name=item_name,
                    properties={
                        "quantity": supply.get("quantity"),
                        "priority": supply.get("priority"),
                    },
                    confidence=0.9,
                    source="logistics_request"
                )
                self.knowledge_graph.add_entity(resource_entity)
                entity_ids.append(resource_id)
                self.graph_builder.link_entities(
                    request_id,
                    resource_id,
                    RelationType.REQUIRES,
                    {"reason": "supplies_needed"},
                    confidence=0.9,
                    source="logistics_request",
                )

            logger.info(f"Processed logistics request: {len(entity_ids)} entities created")
            return entity_ids
        except Exception as e:
            logger.error(f"Error processing logistics request: {e}")
            return []

    def process_path_analysis(self, path_data: Dict[str, Any]) -> List[str]:
        """Process path analysis into KG entities and relations"""
        try:
            logger.info("Processing path analysis data")

            entity_ids: List[str] = []

            results = path_data.get("results", [])
            for result in results:
                path_id_local = result.get("path_id")
                metrics = result.get("metrics", {})
                poi = result.get("poi", {})

                # Create path candidate entity
                path_entity_id = self.graph_builder._generate_id("path_candidate")
                path_entity = Entity(
                    id=path_entity_id,
                    type=EntityType.EVENT,
                    name=f"Path Candidate {path_id_local}",
                    properties={
                        "summary": result.get("summary"),
                        "metrics": metrics,
                    },
                    confidence=0.7,
                    source="path_analysis"
                )
                self.knowledge_graph.add_entity(path_entity)
                entity_ids.append(path_entity_id)

                # Create location entity for POI if present
                if poi:
                    loc_entity_id = self.graph_builder._generate_id("location")
                    loc_entity = Entity(
                        id=loc_entity_id,
                        type=EntityType.LOCATION,
                        name=poi.get("name") or "POI",
                        properties={
                            "poi_type": poi.get("type"),
                            "lat": poi.get("lat"),
                            "lon": poi.get("lon"),
                        },
                        confidence=0.8,
                        source="path_analysis"
                    )
                    self.knowledge_graph.add_entity(loc_entity)
                    entity_ids.append(loc_entity_id)
                    self.graph_builder.link_entities(
                        path_entity_id,
                        loc_entity_id,
                        RelationType.LOCATED_IN,
                        {"relation": "path_to_poi"},
                        confidence=0.8,
                        source="path_analysis",
                    )

            logger.info(f"Processed path analysis: {len(entity_ids)} entities created")
            return entity_ids
        except Exception as e:
            logger.error(f"Error processing path analysis: {e}")
            return []
    
    def analyze_cross_agent_correlations(self) -> Dict[str, Any]:
        """Analyze cross-agent data correlations using Cypher queries"""
        try:
            logger.info("Analyzing cross-agent correlations")
            
            correlations = {
                "photo_interview_correlations": [],
                "person_entity_matches": [],
                "location_correlations": [],
                "history_patterns": [],
                "weather_impacts": [],
                "timeline_analysis": [],
                "priority_areas": [],
                "high_confidence_paths": []
            }
            
            # Use Cypher to find cross-source correlations
            try:
                with self.knowledge_graph.neo4j_driver.session() as session:
                    # 1. Find person entities from different sources that might be the same
                    person_match_query = """
                    MATCH (p1:Entity:Person)
                    WHERE p1.source = "photo_analysis"
                    MATCH (p2:Entity:Person)
                    WHERE p2.source = "interview_analysis"
                    WITH p1, p2, 
                         p1.properties.hair_color as p1_hair,
                         p2.properties.hair_color as p2_hair,
                         p1.properties.clothing as p1_clothing,
                         p2.properties.text as p2_text
                    WHERE (p1_hair IS NOT NULL AND p1_hair = p2_hair)
       OR (p1_clothing IS NOT NULL AND p2_text IS NOT NULL AND p2_text CONTAINS p1_clothing)
                    RETURN p1.id as photo_id, p2.id as interview_id,
                           p1.properties as photo_props, p2.properties as interview_props,
                           CASE 
                             WHEN p1_hair IS NOT NULL AND p1_hair = p2_hair THEN 0.8
                             ELSE 0.6
                           END as match_confidence
                    LIMIT 10
                    """
                    result = session.run(person_match_query)
                    for record in result:
                        correlations["person_entity_matches"].append({
                            "photo_entity_id": record["photo_id"],
                            "interview_entity_id": record["interview_id"],
                            "match_confidence": record["match_confidence"],
                            "photo_properties": dict(record["photo_props"]),
                            "interview_properties": dict(record["interview_props"])
                        })
                    
                    # 2. Find location correlations across sources
                    location_correlation_query = """
                    MATCH (photo:Entity)-[r1:LOCATED_IN|LAST_SEEN]->(loc:Location)
                    WHERE photo.source = "photo_analysis"
                    MATCH (interview:Entity)-[r2:LOCATED_IN|LAST_SEEN]->(loc)
                    WHERE interview.source = "interview_analysis"
                    RETURN DISTINCT loc.id as location_id, loc.name as location_name,
                           count(DISTINCT photo) as photo_count,
                           count(DISTINCT interview) as interview_count
                    LIMIT 20
                    """
                    result = session.run(location_correlation_query)
                    for record in result:
                        correlations["location_correlations"].append({
                            "location_id": record["location_id"],
                            "location_name": record["location_name"],
                            "photo_count": record["photo_count"],
                            "interview_count": record["interview_count"],
                            "confidence": min(1.0, (record["photo_count"] + record["interview_count"]) / 2.0)
                        })
                    
                    # 3. Find high-confidence paths (Person -> Location -> Clue)
                    path_query = """
                    MATCH (person:Entity:Person)-[r1:LAST_SEEN|CONNECTED_TO]->(location:Entity:Location)
                    MATCH (clue:Entity:Clue)-[r2:LOCATED_IN]->(location)
                    WHERE person.confidence > 0.7 AND location.confidence > 0.7 AND clue.confidence > 0.7
                    RETURN person.id as person_id, person.name as person_name,
                           location.id as location_id, location.name as location_name,
                           clue.id as clue_id, clue.name as clue_name,
                           2 as path_length,
                           person.confidence * location.confidence * clue.confidence as total_confidence
                    ORDER BY total_confidence DESC
                    LIMIT 10
                    """
                    result = session.run(path_query)
                    for record in result:
                        correlations["high_confidence_paths"].append({
                            "person": record["person_name"],
                            "location": record["location_name"],
                            "clue": record["clue_name"],
                            "path_length": record["path_length"]
                        })
                    
                    # 4. Analyze historical patterns (if history data exists)
                    history_pattern_query = """
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
                    result = session.run(history_pattern_query)
                    for record in result:
                        correlations["history_patterns"].append({
                            "location_id": record["location_id"],
                            "location_name": record["location_name"],
                            "success_count": record["success_count"],
                            "successful_cases": record["successful_cases"]
                        })
                    
            except Exception as e:
                logger.warning(f"Advanced correlation queries failed, using fallback: {e}")
                # Fallback to simpler queries
                photo_entities = self.knowledge_graph.find_entities(EntityType.CLUE)
                interview_entities = [e for e in photo_entities if "interview" in e.source]
                photo_clues = [e for e in photo_entities if "photo" in e.source]
                
                for interview_clue in interview_entities:
                    for photo_clue in photo_clues:
                        interview_text = interview_clue.properties.get("section", "").lower()
                        photo_detections = photo_clue.properties.get("detections", [])
                        
                        if any("person" in interview_text for _ in [1]) and any(d.get("class") == "person" for d in photo_detections):
                            correlations["photo_interview_correlations"].append({
                                "interview_clue": interview_clue.id,
                                "photo_clue": photo_clue.id,
                                "correlation_type": "person_detection",
                                "confidence": 0.7
                            })
            
            # Analyze timeline
            timeline = self.knowledge_graph.extract_timeline()
            correlations["timeline_analysis"] = timeline
            
            # Analyze priority areas
            area_entities = self.knowledge_graph.find_entities(EntityType.AREA)
            for area in area_entities:
                priority = area.properties.get("priority", "UNKNOWN")
                if priority in ["CRITICAL", "HIGH"]:
                    correlations["priority_areas"].append({
                        "area_id": area.id,
                        "name": area.name,
                        "priority": priority,
                        "urgency": area.properties.get("urgency", "UNKNOWN"),
                        "people_count": area.properties.get("people_count", 0)
                    })
            
            # Use LLM for deep analysis
            if self.openai_client and correlations:
                llm_analysis = self._llm_correlation_analysis(correlations)
                correlations["llm_insights"] = llm_analysis
            
            return correlations
            
        except Exception as e:
            logger.error(f"Error analyzing cross-agent correlations: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _llm_correlation_analysis(self, correlations: Dict[str, Any]) -> Optional[str]:
        """Use LLM for correlation analysis"""
        try:
            system_message = """You are a Search and Rescue expert analyzing correlations between different data sources. 
            Provide insights about patterns, connections, and recommendations based on the correlation data."""
            
            prompt = f"""
            Analyze the following cross-agent correlations and provide insights:
            
            Photo-Interview Correlations: {correlations.get('photo_interview_correlations', [])}
            Timeline Analysis: {correlations.get('timeline_analysis', [])}
            Priority Areas: {correlations.get('priority_areas', [])}
            
            Provide:
            1. Key patterns identified
            2. Most important correlations
            3. Recommended search priorities
            4. Areas requiring further investigation
            """
            
            return self.ask_llm(prompt, system_message)
            
        except Exception as e:
            logger.error(f"Error in LLM correlation analysis: {e}")
            return None
    
    def generate_search_recommendations(self) -> Dict[str, Any]:
        """Generate search recommendations"""
        try:
            logger.info("Generating search recommendations")
            
            recommendations = {
                "immediate_actions": [],
                "search_priorities": [],
                "resource_allocation": [],
                "risk_assessments": [],
                "timeline_suggestions": []
            }
            
            # Analyze graph insights
            insights = self.knowledge_graph.generate_insights()
            
            # Enhanced recommendations using Cypher queries
            # Find high-priority search areas combining multiple signals
            try:
                with self.knowledge_graph.neo4j_driver.session() as session:
                    # Find locations with high confidence from multiple sources
                    priority_location_query = """
                    MATCH (loc:Entity:Location)
                    OPTIONAL MATCH (hist:Entity:Event)-[:SIMILAR_TO*]-(current:Entity:Event)-[:LOCATED_IN|OCCURRED_AT]->(loc)
                    WHERE hist.properties.outcome = "found"
                    OPTIONAL MATCH (path:Entity:Event {source: "path_analysis"})-[:LOCATED_IN]->(loc)
                    OPTIONAL MATCH (person:Entity:Person)-[:LAST_SEEN]->(loc)
                    WITH loc, 
                         count(DISTINCT hist) as history_success_count,
                         count(DISTINCT path) as path_recommendations,
                         count(DISTINCT person) as person_mentions,
                         loc.confidence as base_confidence
                    WHERE history_success_count > 0 OR path_recommendations > 0 OR person_mentions > 0
                    RETURN loc.id as location_id, loc.name as location_name,
                           base_confidence,
                           history_success_count,
                           path_recommendations,
                           person_mentions,
                           (base_confidence + 
                            (history_success_count * 0.3) + 
                            (path_recommendations * 0.2) + 
                            (person_mentions * 0.2)) as priority_score
                    ORDER BY priority_score DESC
                    LIMIT 10
                    """
                    result = session.run(priority_location_query)
                    for record in result:
                        priority = "CRITICAL" if record["priority_score"] > 1.5 else "HIGH"
                        recommendations["search_priorities"].append({
                            "area": record["location_name"],
                            "priority": priority,
                            "reason": f"History success: {record['history_success_count']}, "
                                    f"Path recommendations: {record['path_recommendations']}, "
                                    f"Person mentions: {record['person_mentions']}",
                            "confidence": min(1.0, record["priority_score"] / 2.0),
                            "metadata": {
                                "history_success_count": record["history_success_count"],
                                "path_recommendations": record["path_recommendations"],
                                "person_mentions": record["person_mentions"]
                            }
                        })
            except Exception as e:
                logger.warning(f"Priority location query failed: {e}")
            
            # Generate recommendations based on entity importance
            important_entities = insights.get("most_important_entities", [])
            for entity_info in important_entities:
                # Query entity from Neo4j instead of in-memory dict
                entity_id = entity_info.get("id")
                if entity_id:
                    entities = self.knowledge_graph.find_entities(properties={"id": entity_id})
                    if entities:
                        entity = entities[0]
                        if entity.type == EntityType.AREA:
                            recommendations["search_priorities"].append({
                                "area": entity.name,
                                "priority": entity.properties.get("priority", "UNKNOWN"),
                                "reason": f"High importance score: {entity_info.get('importance', 0):.2f}",
                                "confidence": entity_info.get("confidence", 0.8)
                            })
                        elif entity.type == EntityType.CLUE:
                            recommendations["immediate_actions"].append({
                                "action": f"Investigate clue: {entity.name}",
                                "reason": f"High confidence clue: {entity_info.get('confidence', 0.8):.2f}",
                                "priority": "HIGH" if entity_info.get("confidence", 0) > 0.8 else "MEDIUM"
                            })
            
            # Analyze clusters - use Cypher query instead of in-memory
            clusters = self.knowledge_graph.find_clusters()
            for i, cluster in enumerate(clusters):
                if len(cluster) > 2:  # Only focus on clusters with multiple entities
                    # Query cluster entities from Neo4j
                    cluster_entities = []
                    for entity_id in cluster:
                        entities = self.knowledge_graph.find_entities(properties={"id": entity_id})
                        if entities:
                            cluster_entities.append(entities[0])
                    
                    cluster_types = [e.type.value for e in cluster_entities]
                    
                    if EntityType.PERSON.value in cluster_types and EntityType.LOCATION.value in cluster_types:
                        recommendations["search_priorities"].append({
                            "area": f"Cluster {i+1}",
                            "priority": "HIGH",
                            "reason": "Contains person and location entities",
                            "confidence": 0.8
                        })
            
            # Use LLM to generate comprehensive recommendations
            if self.openai_client:
                llm_recommendations = self._llm_generate_recommendations(recommendations, insights)
                recommendations["llm_recommendations"] = llm_recommendations
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating search recommendations: {e}")
            return {}
    
    def _llm_generate_recommendations(self, recommendations: Dict[str, Any], insights: Dict[str, Any]) -> Optional[str]:
        """Use LLM to generate comprehensive recommendations"""
        try:
            system_message = """You are a Search and Rescue operations expert. Based on the knowledge graph analysis, 
            provide comprehensive search and rescue recommendations."""
            
            prompt = f"""
            Based on the following analysis, provide comprehensive SAR recommendations:
            
            Knowledge Graph Insights:
            - Total entities: {insights.get('total_entities', 0)}
            - Total relations: {insights.get('total_relations', 0)}
            - Entity types: {insights.get('entity_types', {})}
            - Clusters found: {insights.get('clusters', 0)}
            
            Current Recommendations:
            - Immediate actions: {len(recommendations.get('immediate_actions', []))}
            - Search priorities: {len(recommendations.get('search_priorities', []))}
            
            Provide:
            1. Top 3 immediate actions
            2. Search area prioritization
            3. Resource allocation suggestions
            4. Risk mitigation strategies
            5. Timeline recommendations
            """
            
            return self.ask_llm(prompt, system_message)
            
        except Exception as e:
            logger.error(f"Error in LLM recommendation generation: {e}")
            return None
    
    def process_agent_data(self, stream_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data from other agents"""
        try:
            logger.info(f"Processing data from {stream_name}")
            
            # Route to appropriate processing function based on stream name
            entity_ids = []
            
            if "photo.analysis.raw" in stream_name:
                entity_ids = self.process_photo_analysis(data)
            elif "interview.analysis.raw" in stream_name:
                entity_ids = self.process_interview_analysis(data)
            elif "history.out.raw" in stream_name:
                entity_ids = self.process_history_analysis(data)
            elif "weather.forecast.raw" in stream_name:
                entity_ids = self.process_weather_data(data)
            elif "path.analysis.raw" in stream_name:
                entity_ids = self.process_path_analysis(data)
            elif "health.assessment.raw" in stream_name:
                entity_ids = self.process_health_assessment(data)
            elif "logistics.requests.raw" in stream_name:
                entity_ids = self.process_logistics_request(data)
            else:
                logger.warning(f"Unknown stream: {stream_name}")
                return {"status": "ignored", "reason": "unknown_stream"}
            
            # Cache data
            self.recent_data[stream_name] = {
                "data": data,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "entity_ids": entity_ids
            }
            
            # Analyze correlations
            correlations = self.analyze_cross_agent_correlations()
            
            # Generate recommendations
            recommendations = self.generate_search_recommendations()
            
            # Generate graph insights
            insights = self.knowledge_graph.generate_insights()
            
            # Export visualization data if enabled
            # Neo4j Browser is the primary visualization (http://localhost:7474)
            visualization_data = None
            if EXPORT_VISUALIZATIONS:
                try:
                    # Always export JSON data (useful for frontend integration)
                    visualization_data = self.knowledge_graph.export_visualization_data(output_format="json")
                except Exception as e:
                    logger.warning(f"Failed to export visualization: {e}")
            
            result = {
                "status": "processed",
                "stream_source": stream_name,
                "entities_created": len(entity_ids),
                "entity_ids": entity_ids,
                "correlations": correlations,
                "recommendations": recommendations,
                "insights": insights,
                "knowledge_graph_stats": {
                    "clusters": len(self.knowledge_graph.find_clusters())
                },
                "visualization": {
                    "available": visualization_data is not None,
                    "neo4j_browser_url": "http://localhost:7474",
                    "data": visualization_data  # JSON data for frontend integration (always available)
                } if EXPORT_VISUALIZATIONS else None,
                "processed_at": datetime.utcnow().isoformat() + "Z"
            }
            
            # Add to analysis history
            self.analysis_history.append({
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "stream": stream_name,
                "result": result
            })
            
            # Keep history within reasonable bounds
            if len(self.analysis_history) > 100:
                self.analysis_history = self.analysis_history[-50:]
            
            logger.info(f"Successfully processed data from {stream_name}: {len(entity_ids)} entities created")
            return result
            
        except Exception as e:
            logger.error(f"Error processing agent data from {stream_name}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "stream_source": stream_name,
                "processed_at": datetime.utcnow().isoformat() + "Z"
            }

def main():
    """ClueMeister Agent main function"""
    logger.info(f"Initializing {AGENT_NAME}...")
    
    # Initialize Redis connection
    try:
        bus = RedisBus(REDIS_URL)
        logger.info(f"Successfully connected to Redis at {REDIS_URL}")
    except Exception as e:
        logger.critical(f"Failed to connect to Redis: {e}")
        return
    
    # Initialize ClueMeister Agent
    cluemeister = ClueMeisterAgent()
    
    logger.info(f"{AGENT_NAME} starting up. Listening on streams: {INPUT_STREAMS}")
    logger.info(f"Update interval: {UPDATE_INTERVAL_SECONDS} seconds")
    
    # Main processing loop
    try:
        for message in bus.subscribe(
            group_name=f"{AGENT_NAME}-group",
            consumer_name=f"{AGENT_NAME}-consumer",
            streams=INPUT_STREAMS,
            block_ms=UPDATE_INTERVAL_SECONDS * 1000
        ):
            try:
                # Extract message data
                payload = message.payload
                stream_name = message.envelope.target_stream
                
                logger.info(f"Processing message from {stream_name}")
                
                # Process data
                result = cluemeister.process_agent_data(stream_name, payload)
                
                # Publish results to output stream
                output_message = wrap_envelope(
                    payload=result,
                    source_name=AGENT_NAME,
                    source_version=AGENT_VERSION,
                    target_stream=OUTPUT_STREAM
                )
                
                bus.publish(output_message)
                logger.info(f"Published ClueMeister analysis to {OUTPUT_STREAM}")
                
                # Print key information to console
                if result.get("status") == "processed":
                    print(f"\n=== ClueMeister Analysis ===")
                    print(f"Stream: {stream_name}")
                    print(f"Entities created: {result.get('entities_created', 0)}")
                    print(f"Total entities in graph: {result.get('knowledge_graph_stats', {}).get('total_entities', 0)}")
                    print(f"Clusters found: {result.get('knowledge_graph_stats', {}).get('clusters', 0)}")
                    
                    # Display important recommendations
                    recommendations = result.get("recommendations", {})
                    if recommendations.get("immediate_actions"):
                        print(f"Immediate actions: {len(recommendations['immediate_actions'])}")
                    if recommendations.get("search_priorities"):
                        print(f"Search priorities: {len(recommendations['search_priorities'])}")
                    
                    print("============================\n")
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                
                # Send error to dead letter stream
                error_payload = {
                    "failed_agent": f"{AGENT_NAME}:{AGENT_VERSION}",
                    "error_message": str(e),
                    "error_type": type(e).__name__,
                    "context": "Failed while processing agent data"
                }
                
                error_message = wrap_envelope(
                    payload=error_payload,
                    source_name=AGENT_NAME,
                    source_version=AGENT_VERSION,
                    target_stream=DEAD_LETTER_STREAM
                )
                
                bus.publish(error_message)
                logger.error(f"Sent error to dead letter stream: {DEAD_LETTER_STREAM}")
                
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down gracefully")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}")
        time.sleep(UPDATE_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()


