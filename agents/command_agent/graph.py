#!/usr/bin/env python3
"""
SAR Command Agent - LangGraph Definition

This module defines the state machine for the SAR command agent using LangGraph.
The graph implements a Supervisor pattern where:
1. Supervisor node decides which specialists to consult
2. Specialist nodes gather data from their respective Redis streams
3. Synthesizer node combines all analyses into a final response

Architecture:
    User Query → Supervisor → [Weather, Health, History, Photo, Path] → Synthesizer → Response
"""

import os
import json
import logging
from typing import TypedDict, Annotated, Literal, Sequence, Optional, Dict, Any, List
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
import uuid

from .tools import (
    ALL_TOOLS,
    get_weather_data,
    get_health_assessment,
    get_history_cases,
    get_photo_analysis,
    get_path_analysis,
    get_logistics_status,
    get_interview_analysis,
    get_cluemeister_analysis,
)

# Configuration
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("COMMAND_AGENT_MODEL", "gemini-2.5-flash")
TEMPERATURE = float(os.getenv("COMMAND_AGENT_TEMPERATURE", "0.7"))

# Logger
logger = logging.getLogger("command-agent-graph")


# ============================================================================
# State Definition
# ============================================================================

class SARState(TypedDict):
    """
    State for the SAR Command Agent graph.
    
    Attributes:
        messages: Conversation history
        query: Original user query
        specialists_to_consult: List of specialists the supervisor wants to consult
        weather_analysis: Analysis from weather specialist
        health_analysis: Analysis from health specialist
        history_analysis: Analysis from history specialist
        photo_analysis: Analysis from photo specialist
        path_analysis: Analysis from path specialist
        final_response: Synthesized final response
        iteration: Current iteration count (to prevent infinite loops)
        
        # Task dispatch tracking
        pending_tasks: List of dispatched task IDs
        task_results: Results from completed tasks
        dispatched_to: Which agents have received tasks
        use_dispatch_mode: Whether to use active task dispatch (vs passive read)
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    query: str
    specialists_to_consult: list[str]
    weather_analysis: Optional[str]
    health_analysis: Optional[str]
    history_analysis: Optional[str]
    photo_analysis: Optional[str]
    path_analysis: Optional[str]
    final_response: Optional[str]
    iteration: int
    # Task dispatch fields
    pending_tasks: Optional[List[str]]
    task_results: Optional[Dict[str, Any]]
    dispatched_to: Optional[List[str]]
    use_dispatch_mode: Optional[bool]
    file_urls: Optional[List[Dict[str, Any]]]  # uploaded file context from query


# ============================================================================
# LLM Setup
# ============================================================================

def get_llm(with_tools: bool = False) -> ChatGoogleGenerativeAI:
    """Create LLM instance using Google Gemini."""
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        google_api_key=GOOGLE_API_KEY,
    )
    if with_tools:
        # Bind only dispatch tools (exclude wait_for_task_results — handled by system)
        from .tools import DISPATCH_TOOLS, wait_for_task_results
        supervisor_tools = [t for t in DISPATCH_TOOLS if t is not wait_for_task_results]
        return llm.bind_tools(supervisor_tools)
    return llm


# ============================================================================
# System Prompts
# ============================================================================

SUPERVISOR_PROMPT = """You are the SAR (Search and Rescue) Command Center Supervisor.
Your role is to analyze user queries about search and rescue operations and determine which specialists to consult.

Available specialists:
- weather: Weather conditions and their impact on search operations
- health: Health risk assessment for missing persons
- history: Historical SAR cases and patterns
- photo: Photo/image analysis results
- path: Terrain and path analysis

Based on the user's query, decide which specialists would be most helpful.
Return a JSON object with the following format:
{
    "reasoning": "Brief explanation of why you chose these specialists",
    "specialists": ["specialist1", "specialist2", ...]
}

If the query is general or covers multiple areas, include all relevant specialists.
If the query is specific (e.g., "what's the weather?"), only include the relevant specialist.
Always include at least one specialist.
"""

SPECIALIST_PROMPTS = {
    "weather": """You are a Weather Analysis Specialist for SAR operations.
Analyze the weather data and explain how conditions affect search and rescue:
- Temperature and exposure risks
- Visibility and search effectiveness
- Wind and terrain navigation
- Precipitation and safety concerns
Provide actionable recommendations for the search team.""",

    "health": """You are a Health Assessment Specialist for SAR operations.
Analyze health risk data and provide assessment:
- Medical urgency based on subject's conditions
- Time-critical factors
- Survival probability considerations
- Recommended medical preparations
Provide clear risk levels and prioritization guidance.""",

    "history": """You are a Historical Case Analyst for SAR operations.
Analyze similar historical cases and extract insights:
- Similar case outcomes and timelines
- Effective search strategies from past cases
- Common patterns and behaviors
- Lessons learned and pitfalls to avoid
Provide strategic recommendations based on historical data.""",

    "photo": """You are a Photo Analysis Specialist for SAR operations.
Analyze image detection results:
- Identified objects and persons
- Potential clue locations
- Area coverage assessment
- Recommendations for further imagery needs
Highlight any findings that could aid the search.""",

    "path": """You are a Terrain and Path Analysis Specialist for SAR operations.
Analyze terrain and path data:
- Terrain difficulty and accessibility
- Recommended search routes
- Hazard identification
- Resource deployment by terrain type
Provide route planning recommendations.""",
}

SYNTHESIZER_PROMPT = """You are the SAR Command Center Synthesizer.
Your role is to combine analyses from multiple specialists into a coherent, actionable response.

You have received the following analyses:
{analyses}

Based on all available information, provide a comprehensive response that:
1. Summarizes the key findings from each specialist
2. Identifies any conflicts or concerns across analyses
3. Provides prioritized, actionable recommendations
4. Highlights any urgent items requiring immediate attention

Keep your response focused and practical for SAR operations.
Address the user's original query directly while incorporating all relevant insights.

User's original query: {query}
"""


SUPERVISOR_DISPATCH_PROMPT = """You are the SAR Command Center Supervisor.
Actively dispatch tasks to specialist agents using the dispatch_* tools.

RULES:
- Call dispatch_history_query only if the query asks about past SAR cases, historical incidents, similar cases, or precedents. Do NOT call it for weather, health, or witness statement queries.
- Call dispatch_weather_query if weather, terrain, environment, or exposure is relevant. If the query mentions a specific past date or day (e.g. "last Monday", "on April 10th", "3 days ago"), convert it to YYYY-MM-DD and pass as the date argument.
- Call dispatch_health_assessment if person health, age, or medical info is mentioned.
- Call dispatch_path_analysis if location, route, or terrain is relevant.
- Call dispatch_interview_analysis if: (a) file_urls contains a PDF, OR (b) the query contains witness testimony, statements of what someone observed, interview transcripts, or any narrative account of seeing the missing person. Pass the text as transcript_text.
- If file_urls contains images → call dispatch_photo_analysis with that image_url.
- Default coordinates if no location given: lat=35.2828, lon=-120.6596.
- Do NOT call wait_for_task_results — the system collects results automatically.
- Output ONLY tool calls, no prose or explanation.
"""


# ============================================================================
# Graph Nodes
# ============================================================================

def supervisor_node(state: SARState) -> SARState:
    """
    Supervisor node — uses tool-calling LLM to actively dispatch tasks to specialists,
    then waits for all results via TaskTracker.
    """
    import re as _re
    from langchain_core.messages import ToolMessage
    from .tools import TOOL_MAP
    from .task_tracker import get_tracker

    logger.info("Supervisor: Dispatching tasks to agents...")

    # --- Step 1: Fast structured context extraction (no tools, single call) ---
    ctx_llm = get_llm(with_tools=False)
    ctx = {}
    try:
        ctx_resp = ctx_llm.invoke([HumanMessage(content=(
            "Extract from this SAR query and respond in JSON only (no markdown):\n"
            '{"lat": float_or_null, "lon": float_or_null, "person": "description_or_null", "themes": ["list"]}\n\n'
            f"Query: {state['query']}\n"
            f"Files: {json.dumps(state.get('file_urls') or [])}"
        ))])
        import re as _re2
        match = _re2.search(r'\{.*\}', ctx_resp.content, _re2.DOTALL)
        if match:
            ctx = json.loads(match.group())
    except Exception as _ctx_err:
        logger.warning(f"Supervisor: context extraction failed: {_ctx_err}")

    logger.info(f"Supervisor: extracted context: {ctx}")

    # --- Step 2: Agentic tool-call dispatch loop ---
    llm = get_llm(with_tools=True)

    enriched_query = (
        f"User query: {state['query']}\n"
        f"Extracted: lat={ctx.get('lat')}, lon={ctx.get('lon')}, person={ctx.get('person')}\n"
        f"File context: {json.dumps(state.get('file_urls') or [])}\n"
        f"Themes: {ctx.get('themes', ['history'])}"
    )
    messages = [
        SystemMessage(content=SUPERVISOR_DISPATCH_PROMPT),
        HumanMessage(content=enriched_query),
    ]

    dispatched_task_ids: List[str] = []

    for _ in range(5):  # agentic tool-call loop, max 5 rounds
        response = llm.invoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        for tc in tool_calls:
            fn = TOOL_MAP.get(tc["name"])
            if fn:
                result = fn.invoke(tc["args"])
                result_str = str(result)
                ids = _re.findall(r"TASK-[\w-]+", result_str)
                dispatched_task_ids.extend(ids)
                logger.info(f"Supervisor: dispatched {tc['name']} → {ids}")
                messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))
            else:
                logger.warning(f"Supervisor: unknown tool {tc['name']}")

    # Wait for all dispatched tasks (blocking — runs in command-agent thread, not async)
    task_results: Dict[str, Any] = {}
    if dispatched_task_ids:
        tracker = get_tracker()
        task_results = tracker.wait_for_tasks(dispatched_task_ids, timeout=60)
        logger.info(f"Supervisor: collected {len(task_results)}/{len(dispatched_task_ids)} results")
    else:
        logger.warning("Supervisor: no tasks dispatched, falling back to passive read")

    return {
        **state,
        "specialists_to_consult": [],
        "task_results": task_results,
        "dispatched_to": dispatched_task_ids,
        "iteration": state.get("iteration", 0) + 1,
    }


def create_specialist_node(specialist_name: str):
    """Factory function to create specialist nodes."""
    
    tool_map = {
        "weather": get_weather_data,
        "health": get_health_assessment,
        "history": get_history_cases,
        "photo": get_photo_analysis,
        "path": get_path_analysis,
    }
    
    analysis_key_map = {
        "weather": "weather_analysis",
        "health": "health_analysis",
        "history": "history_analysis",
        "photo": "photo_analysis",
        "path": "path_analysis",
    }
    
    def specialist_node(state: SARState) -> SARState:
        """Specialist node - gathers and analyzes domain-specific data."""
        
        # Check if this specialist should be consulted
        if specialist_name not in state.get("specialists_to_consult", []):
            logger.info(f"{specialist_name.capitalize()}: Skipped (not requested)")
            return state
        
        logger.info(f"{specialist_name.capitalize()}: Gathering data...")
        
        # Get the tool and fetch data
        tool = tool_map.get(specialist_name)
        if not tool:
            logger.error(f"{specialist_name}: No tool found")
            return state
        
        # Invoke the tool to get data
        raw_data = tool.invoke({})
        
        # If no data, skip analysis
        if "No data" in raw_data or "Error" in raw_data:
            logger.warning(f"{specialist_name.capitalize()}: {raw_data}")
            return {
                **state,
                analysis_key_map[specialist_name]: f"No data available from {specialist_name} agent."
            }
        
        # Use LLM to analyze the data
        llm = get_llm()
        prompt = SPECIALIST_PROMPTS.get(specialist_name, "Analyze the following data:")
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Data:\n{raw_data}\n\nUser query: {state['query']}")
        ]
        
        response = llm.invoke(messages)
        analysis = response.content
        
        logger.info(f"{specialist_name.capitalize()}: Analysis complete")
        
        return {
            **state,
            analysis_key_map[specialist_name]: analysis
        }
    
    return specialist_node


def synthesizer_node(state: SARState) -> SARState:
    """
    Synthesizer node — combines task_results (dispatch mode) or legacy specialist
    analysis fields into a final response via LLM.
    """
    logger.info("Synthesizer: Combining analyses...")

    analyses = []

    # Dispatch mode: read from task_results populated by supervisor
    for task_id, result in (state.get("task_results") or {}).items():
        if isinstance(result, dict) and "error" not in result:
            agent = result.get("agent", task_id)
            analyses.append(f"**{agent} Analysis:**\n{json.dumps(result, default=str)[:2000]}")
        elif isinstance(result, dict):
            logger.warning(f"Synthesizer: task {task_id} returned error: {result}")

    # Fallback: legacy passive-read specialist fields (when dispatch returned nothing)
    if not analyses:
        for field_key, label in [
            ("weather_analysis", "Weather"),
            ("health_analysis", "Health"),
            ("history_analysis", "History"),
            ("photo_analysis", "Photo"),
            ("path_analysis", "Path"),
        ]:
            if state.get(field_key):
                analyses.append(f"**{label} Analysis:**\n{state[field_key]}")

    if not analyses:
        logger.warning("Synthesizer: No analyses available from any source")
        return {
            **state,
            "final_response": (
                "No agent data available. Please ensure specialist agents are running "
                "and connected to Redis."
            ),
        }

    llm = get_llm()
    prompt = SYNTHESIZER_PROMPT.format(
        analyses="\n\n".join(analyses),
        query=state["query"],
    )
    response = llm.invoke([HumanMessage(content=prompt)])

    logger.info("Synthesizer: Response generated")
    return {
        **state,
        "final_response": response.content,
        "messages": list(state.get("messages", [])) + [AIMessage(content=response.content)],
    }


# ============================================================================
# Routing Logic
# ============================================================================

def route_after_supervisor(state: SARState) -> str:
    """Route after supervisor — dispatch mode goes straight to synthesizer."""
    # In dispatch mode the supervisor already waited for all task results
    if state.get("use_dispatch_mode", True):
        return "synthesizer"

    # Legacy passive-read path
    specialists = state.get("specialists_to_consult", [])
    if not specialists:
        return "synthesizer"
    priority_order = ["weather", "health", "history", "photo", "path"]
    for spec in priority_order:
        if spec in specialists:
            return spec
    return "synthesizer"


def route_after_specialist(current_specialist: str):
    """Factory function to create routing logic after each specialist."""
    
    priority_order = ["weather", "health", "history", "photo", "path"]
    
    def router(state: SARState) -> str:
        specialists = state.get("specialists_to_consult", [])
        
        # Find next specialist in priority order
        found_current = False
        for spec in priority_order:
            if spec == current_specialist:
                found_current = True
                continue
            if found_current and spec in specialists:
                return spec
        
        # No more specialists, go to synthesizer
        return "synthesizer"
    
    return router


# ============================================================================
# Graph Builder
# ============================================================================

def build_sar_graph() -> StateGraph:
    """
    Build the SAR command agent graph.
    
    Graph structure:
        supervisor → weather → health → history → photo → path → synthesizer → END
                  ↘         ↘          ↘          ↘       ↘
                   (skip if not in specialists_to_consult)
    """
    
    # Create graph
    graph = StateGraph(SARState)
    
    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("weather", create_specialist_node("weather"))
    graph.add_node("health", create_specialist_node("health"))
    graph.add_node("history", create_specialist_node("history"))
    graph.add_node("photo", create_specialist_node("photo"))
    graph.add_node("path", create_specialist_node("path"))
    graph.add_node("synthesizer", synthesizer_node)
    
    # Set entry point
    graph.set_entry_point("supervisor")
    
    # Add edges from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "weather": "weather",
            "health": "health",
            "history": "history",
            "photo": "photo",
            "path": "path",
            "synthesizer": "synthesizer",
        }
    )
    
    # Add edges between specialists
    for i, spec in enumerate(["weather", "health", "history", "photo", "path"]):
        graph.add_conditional_edges(
            spec,
            route_after_specialist(spec),
            {
                "weather": "weather",
                "health": "health",
                "history": "history",
                "photo": "photo",
                "path": "path",
                "synthesizer": "synthesizer",
            }
        )
    
    # Synthesizer goes to END
    graph.add_edge("synthesizer", END)
    
    return graph


# Compile the graph with checkpointer for session persistence
checkpointer = MemorySaver()
sar_graph = build_sar_graph().compile(checkpointer=checkpointer)


# ============================================================================
# Entry Point
# ============================================================================

def run_query(query: str, session_id: Optional[str] = None,
              file_urls: Optional[List[Dict[str, Any]]] = None,
              verbose: bool = False) -> str:
    """
    Run a query through the SAR command agent graph.
    
    Args:
        query: User's question or request
        session_id: Optional session ID for multi-turn conversations.
                    If provided, conversation history is preserved.
        verbose: Whether to print intermediate steps
        
    Returns:
        Final synthesized response
    """
    # Generate session_id if not provided (single-turn mode)
    if session_id is None:
        session_id = str(uuid.uuid4())
        logger.info(f"New session created: {session_id}")
    else:
        logger.info(f"Continuing session: {session_id}")
    
    # Config for checkpointing - thread_id enables session persistence
    config = {"configurable": {"thread_id": session_id}}
    
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "query": query,
        "specialists_to_consult": [],
        "weather_analysis": None,
        "health_analysis": None,
        "history_analysis": None,
        "photo_analysis": None,
        "path_analysis": None,
        "final_response": None,
        "iteration": 0,
        # Task dispatch fields
        "pending_tasks": [],
        "task_results": {},
        "dispatched_to": [],
        "use_dispatch_mode": True,
        "file_urls": file_urls or [],
    }
    
    if verbose:
        # Stream with intermediate steps
        for event in sar_graph.stream(initial_state, config=config):
            for node_name, node_state in event.items():
                print(f"\n--- {node_name.upper()} ---")
                if node_name == "supervisor":
                    print(f"Specialists to consult: {node_state.get('specialists_to_consult', [])}")
                elif node_name == "synthesizer":
                    print(f"Final response generated")
                else:
                    analysis_key = f"{node_name}_analysis"
                    if node_state.get(analysis_key):
                        print(f"Analysis available: {len(node_state[analysis_key])} chars")
        # Get final state for verbose mode
        final_state = sar_graph.invoke(initial_state, config=config)
        return final_state.get("final_response", "No response generated")
    else:
        # Run without streaming
        final_state = sar_graph.invoke(initial_state, config=config)
        return final_state.get("final_response", "No response generated")


def get_session_history(session_id: str) -> list:
    """
    Get conversation history for a session.
    
    Args:
        session_id: Session ID to retrieve history for
        
    Returns:
        List of messages in the session
    """
    config = {"configurable": {"thread_id": session_id}}
    try:
        state = sar_graph.get_state(config)
        if state and state.values:
            messages = state.values.get("messages", [])
            return [
                {"role": "user" if isinstance(m, HumanMessage) else "assistant", 
                 "content": m.content}
                for m in messages
            ]
    except Exception as e:
        logger.warning(f"Could not retrieve session history: {e}")
    return []


if __name__ == "__main__":
    # Test the graph
    logging.basicConfig(level=logging.INFO)
    
    test_query = "What's the current weather and how does it affect our search operations?"
    print(f"Query: {test_query}\n")
    
    response = run_query(test_query, verbose=True)
    print(f"\n=== FINAL RESPONSE ===\n{response}")
