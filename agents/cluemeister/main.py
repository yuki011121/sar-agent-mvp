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

# 导入知识图谱
from knowledge_graph import (
    KnowledgeGraph, ClueMeisterGraphBuilder, 
    EntityType, RelationType, Entity, Relation
)

# 导入Redis通信
from shared import RedisBus, wrap_envelope, parse_message_from_stream

# 加载环境变量
load_dotenv()

# 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", 10))
AGENT_NAME = "cluemeister-agent"
AGENT_VERSION = "cluemeister-agent-v1.0"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Redis流配置
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
        self.openai_api_key = OPENAI_API_KEY
        
        # Initialize knowledge graph
        self.knowledge_graph = KnowledgeGraph()
        self.graph_builder = ClueMeisterGraphBuilder(self.knowledge_graph)
        
        # Initialize OpenAI client
        if self.openai_api_key:
            try:
                import openai
                self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
                logger.info("OpenAI client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.openai_client = None
        else:
            logger.warning("No OpenAI API key found. Using fallback analysis.")
            self.openai_client = None
        
        # Data cache
        self.recent_data = {}
        self.analysis_history = []
        
        logger.info(f"ClueMeister Agent initialized with knowledge graph")
    
    def ask_llm(self, prompt: str, system_message: str = None) -> Optional[str]:
        """Call LLM for analysis"""
        if not self.openai_client:
            logger.warning("No OpenAI client available. Using fallback.")
            return None
        
        try:
            messages = []
            if system_message:
                messages.append({"role": "system", "content": system_message})
            messages.append({"role": "user", "content": prompt})
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.3,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None
    
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
        """Process history analysis data"""
        try:
            logger.info("Processing history analysis data")
            
            entity_ids = []
            
            # Process historical cases
            summary = history_data.get("summary", "")
            actions = history_data.get("actions", "")
            
            if summary or actions:
                case_id = self.graph_builder._generate_id("historical_case")
                case_entity = Entity(
                    id=case_id,
                    type=EntityType.EVENT,
                    name="Historical SAR Case",
                    properties={
                        "summary": summary,
                        "actions": actions,
                        "source_type": "historical_analysis"
                    },
                    confidence=0.8,
                    source="history_agent"
                )
                self.knowledge_graph.add_entity(case_entity)
                entity_ids.append(case_id)
            
            logger.info(f"Processed history analysis: {len(entity_ids)} entities created")
            return entity_ids
            
        except Exception as e:
            logger.error(f"Error processing history analysis: {e}")
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
    
    def analyze_cross_agent_correlations(self) -> Dict[str, Any]:
        """Analyze cross-agent data correlations"""
        try:
            logger.info("Analyzing cross-agent correlations")
            
            correlations = {
                "photo_interview_correlations": [],
                "history_patterns": [],
                "weather_impacts": [],
                "timeline_analysis": [],
                "priority_areas": []
            }
            
            # Analyze photo and interview correlations
            photo_entities = self.knowledge_graph.find_entities(EntityType.CLUE)
            interview_entities = [e for e in photo_entities if "interview" in e.source]
            photo_clues = [e for e in photo_entities if "photo" in e.source]
            
            for interview_clue in interview_entities:
                for photo_clue in photo_clues:
                    # Check for common keywords
                    interview_text = interview_clue.properties.get("section", "").lower()
                    photo_detections = photo_clue.properties.get("detections", [])
                    
                    # Simple keyword matching
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
            
            # Generate recommendations based on entity importance
            important_entities = insights.get("most_important_entities", [])
            for entity_info in important_entities:
                entity = self.knowledge_graph.entities.get(entity_info["id"])
                if entity:
                    if entity.type == EntityType.AREA:
                        recommendations["search_priorities"].append({
                            "area": entity.name,
                            "priority": entity.properties.get("priority", "UNKNOWN"),
                            "reason": f"High importance score: {entity_info['importance']:.2f}",
                            "confidence": entity_info["confidence"]
                        })
                    elif entity.type == EntityType.CLUE:
                        recommendations["immediate_actions"].append({
                            "action": f"Investigate clue: {entity.name}",
                            "reason": f"High confidence clue: {entity_info['confidence']:.2f}",
                            "priority": "HIGH" if entity_info["confidence"] > 0.8 else "MEDIUM"
                        })
            
            # Analyze clusters
            clusters = self.knowledge_graph.find_clusters()
            for i, cluster in enumerate(clusters):
                if len(cluster) > 2:  # Only focus on clusters with multiple entities
                    cluster_entities = [self.knowledge_graph.entities[eid] for eid in cluster if eid in self.knowledge_graph.entities]
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
            
            result = {
                "status": "processed",
                "stream_source": stream_name,
                "entities_created": len(entity_ids),
                "entity_ids": entity_ids,
                "correlations": correlations,
                "recommendations": recommendations,
                "insights": insights,
                "knowledge_graph_stats": {
                    "total_entities": len(self.knowledge_graph.entities),
                    "total_relations": len(self.knowledge_graph.relations),
                    "clusters": len(self.knowledge_graph.find_clusters())
                },
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


