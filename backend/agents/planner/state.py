from typing import TypedDict, Optional, Annotated
from langgraph.graph.message import add_messages
from backend.agents.planner.schemas import PlanOutput

# =============================================================================
# STATE SCHEMA
# =============================================================================

class PlannerState(TypedDict):
    """
    State schema for the Planner Subgraph.
    
    Follows LangGraph conventions with annotated message accumulation.
    """
    # Message history with automatic accumulation
    messages: Annotated[list, add_messages]
    
    # Internal working memory for the reasoning process
    internal_scratchpad: Optional[str]
    
    # Final structured output (populated by Drafting node)
    final_plan_output: Optional[PlanOutput]
    
    # Iteration tracking for safety limits
    iteration_count: int
