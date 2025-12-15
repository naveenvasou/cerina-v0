"""
Main LangGraph Workflow for Cerina CBT Agent.

Flow:
  router → planner → [HITL: await_plan_approval] → draftsman → critic ⟷ reviser (loop) → synthesizer → END
                              ↓
                    (user approves/revises/rejects)

Human-in-the-Loop:
- After planner completes, workflow halts for user approval
- User can: Approve (→ draftsman), Revise (→ planner), or Reject (→ END)

The critic-reviser loop runs until:
1. All 3 critics approve the draft, OR
2. Maximum iterations (default 3) are reached

Checkpointing:
- Uses PostgresSaver for persistent state (with MemorySaver fallback)
- Enables resumption of interrupted workflows across server restarts
- Each session gets a unique thread_id
"""

import os
import json
from typing import Optional
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from backend.agents.router import RouterAgent
from backend.agents.planner import PlannerAgent
from backend.agents.draftsman import DraftsmanAgent
from backend.agents.critic import CriticAgent
from backend.agents.reviser import ReviserAgent
from backend.agents.synthesizer import PresentationSynthesizerAgent
from backend.state import AgentState
from backend.settings import settings


# --- Configuration ---
MAX_REFLECTION_ITERATIONS = 3  # Maximum critique-revision cycles


# --- Instantiate Agents ---
router = RouterAgent()
planner = PlannerAgent()
draftsman = DraftsmanAgent()
critic = CriticAgent()
reviser = ReviserAgent()
synthesizer = PresentationSynthesizerAgent()


# --- Node Functions ---

def call_router(state: AgentState):
    """Entry point - classifies user intent and routes accordingly."""
    print("--- CALLING ROUTER ---")
    return router.invoke(state)


def call_planner(state: AgentState):
    """Generates the clinical plan for the CBT exercise."""
    print("--- CALLING PLANNER ---")
    return planner.invoke(state)


async def call_draftsman(state: AgentState):
    """Drafts the CBT exercise based on the plan."""
    print("--- CALLING DRAFTSMAN ---")
    import asyncio
    result = await asyncio.to_thread(draftsman.invoke, state)
    # Initialize max_iterations if not set
    if "max_iterations" not in result:
        result["max_iterations"] = MAX_REFLECTION_ITERATIONS
    return result


async def call_critic(state: AgentState):
    """
    Evaluates the current draft with 3 specialized critics.
    Returns critique_document, critique_approved, critique_data.
    """
    print(f"--- CALLING CRITIC (Iteration {state.get('reflection_iteration', 1)}) ---")
    import asyncio
    return await asyncio.to_thread(critic.invoke, state)


async def call_reviser(state: AgentState):
    """
    Revises the draft based on critique feedback.
    Updates current_draft and increments reflection_iteration.
    """
    print(f"--- CALLING REVISER (Iteration {state.get('reflection_iteration', 1)}) ---")
    import asyncio
    return await asyncio.to_thread(reviser.invoke, state)


async def call_synthesizer(state: AgentState):
    """
    Final formatting pass for approved draft.
    Produces the final_presentation.
    """
    print("--- CALLING SYNTHESIZER ---")
    import asyncio
    return await asyncio.to_thread(synthesizer.invoke, state)


def respond(state: AgentState):
    """Terminal node for direct conversation responses (no state change needed)."""
    print("--- DIRECT RESPONSE ---")
    return {}


def await_plan_approval(state: AgentState):
    """
    Human-in-the-Loop interrupt point after planner.
    
    Emits the plan for user approval, then blocks until user resumes.
    User can: Approve (→ draftsman), Revise (→ planner), or Reject (→ END).
    """
    from backend.events import get_emitter
    
    print("--- AWAITING PLAN APPROVAL ---")
    
    # Check if we're resuming from a previous interrupt (Bug #4 fix)
    # If hitl_pending is already True, we're resuming - don't emit again
    already_pending = state.get("hitl_pending", False)
    
    # Emit plan_pending_approval event for frontend (only on first entry)
    emitter = get_emitter()
    if emitter and not already_pending:
        plan_json = state.get("plan", "")
        revision_count = state.get("plan_revision_count", 0)
        
        # Try to extract user_preview from plan JSON
        user_preview = ""
        try:
            plan_data = json.loads(plan_json) if isinstance(plan_json, str) else plan_json
            user_preview = plan_data.get("user_preview", "")
        except (json.JSONDecodeError, AttributeError):
            user_preview = ""
        
        # Customize message based on whether this is a revision
        if revision_count > 0:
            default_preview = f"Revised plan (version {revision_count + 1}) is ready for review."
        else:
            default_preview = "Your clinical exercise plan is ready for review."
        
        emitter.emit_plan_pending_approval(
            agent="planner",
            plan_json=plan_json,
            user_preview=user_preview if user_preview else default_preview
        )
        
        # IMPORTANT: We need the interrupt() to happen AFTER emitting the event
        # but the checkpoint must include hitl_pending=True so on resume we don't emit again.
        # We return hitl_pending=True as a partial state update, then call interrupt().
        # However, LangGraph doesn't support partial returns before interrupt.
        # The workaround is handled in websocket_routes.py by filtering duplicate events.
    
    # Block execution until user provides decision via Command(resume=...)
    # The value returned from interrupt() is what the user sends when resuming
    user_decision = interrupt(value={
        "type": "plan_approval_required",
        "plan": state.get("plan"),
        "message": "Please review the plan and approve, request revision, or reject."
    })
    
    # user_decision structure: {"decision": "approved" | "revised" | "rejected", "feedback": "..."}
    decision = user_decision.get("decision", "rejected") if isinstance(user_decision, dict) else "rejected"
    feedback = user_decision.get("feedback", "") if isinstance(user_decision, dict) else ""
    
    print(f"📋 User decision: {decision}")
    if feedback:
        print(f"   Feedback: {feedback[:100]}..." if len(feedback) > 100 else f"   Feedback: {feedback}")
    
    # Update revision count if user requested revision
    revision_count = state.get("plan_revision_count", 0)
    if decision == "revised":
        revision_count += 1
    
    return {
        "hitl_pending": False,
        "hitl_decision": decision,
        "hitl_feedback": feedback,
        "plan_revision_count": revision_count
    }


# --- Routing Logic ---

def route_decision(state: AgentState) -> str:
    """Conditional edge function - routes based on router's classification."""
    route = state.get("route", "planner")
    if route == "conversation":
        return "respond"
    elif route == "draftsman":
        return "draftsman"
    else:
        return "planner"


def should_continue_reflection(state: AgentState) -> str:
    """
    Routing function for the critique-revision loop.
    
    Returns:
        "synthesizer" - If approved or max iterations reached
        "reviser" - If more revisions needed and iterations remain
    """
    critique_approved = state.get("critique_approved", False)
    reflection_iteration = state.get("reflection_iteration", 1)
    max_iterations = state.get("max_iterations", MAX_REFLECTION_ITERATIONS)
    
    # If approved, proceed to synthesis
    if critique_approved:
        print(f"✅ Draft approved after {reflection_iteration} iteration(s)")
        return "synthesizer"
    
    # If max iterations reached, proceed anyway
    if reflection_iteration >= max_iterations:
        print(f"⚠️ Max iterations ({max_iterations}) reached, proceeding to synthesis")
        return "synthesizer"
    
    # Otherwise, continue revision loop
    print(f"🔄 Revision needed (iteration {reflection_iteration}/{max_iterations})")
    return "reviser"


def route_after_approval(state: AgentState) -> str:
    """
    Route based on user's HITL approval decision.
    
    Returns:
        "draftsman" - User approved the plan
        "planner" - User requested revision (loops back with feedback)
        END - User rejected the plan
    """
    decision = state.get("hitl_decision")
    if decision == "approved":
        print("✅ Plan approved - proceeding to Draftsman")
        return "draftsman"
    elif decision == "revised":
        print(f"✏️ Revision requested - returning to Planner (attempt {state.get('plan_revision_count', 1)})")
        return "planner"
    else:
        print("❌ Plan rejected - terminating workflow")
        return END


# --- Graph Construction ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("router", call_router)
workflow.add_node("planner", call_planner)
workflow.add_node("await_plan_approval", await_plan_approval)  # HITL interrupt point
workflow.add_node("draftsman", call_draftsman)
workflow.add_node("critic", call_critic)
workflow.add_node("reviser", call_reviser)
workflow.add_node("synthesizer", call_synthesizer)
workflow.add_node("respond", respond)

# Set Entry Point to Router (the conversational layer)
workflow.set_entry_point("router")

# Conditional edge from router based on intent classification
workflow.add_conditional_edges(
    "router",
    route_decision,
    {
        "respond": "respond",
        "planner": "planner",
        "draftsman": "draftsman"
    }
)

# Linear edges for pipeline paths
workflow.add_edge("planner", "await_plan_approval")  # Planner → HITL Approval
workflow.add_edge("draftsman", "critic")             # Draftsman → Critic (first evaluation)

# Conditional edge from HITL approval: approve, revise, or reject
workflow.add_conditional_edges(
    "await_plan_approval",
    route_after_approval,
    {
        "draftsman": "draftsman",
        "planner": "planner",  # Revision loop back to planner
        END: END
    }
)

# Conditional edge from critic: either revise or synthesize
workflow.add_conditional_edges(
    "critic",
    should_continue_reflection,
    {
        "reviser": "reviser",
        "synthesizer": "synthesizer"
    }
)

# Reviser loops back to critic
workflow.add_edge("reviser", "critic")

# Synthesizer and respond are terminal
workflow.add_edge("synthesizer", END)
workflow.add_edge("respond", END)


# --- Checkpointer Setup ---
# Uses PostgresSaver (from database.py) when DATABASE_URL is set
# Falls back to MemorySaver for local dev without database
from backend.database import get_checkpointer

# Compile with the global checkpointer
graph = workflow.compile(checkpointer=get_checkpointer())


def get_compiled_graph():
    """
    Get a compiled graph with the current checkpointer.
    
    Use this if you need to refresh the checkpointer after init_checkpointer() is called.
    """
    return workflow.compile(checkpointer=get_checkpointer())



# --- Execution Test (Optional) ---
if __name__ == "__main__":
    from langchain_core.messages import HumanMessage
    
    print("Starting Workflow...")
    print("=" * 60)
    
    inputs = {
        "user_query": "Create a graded exposure hierarchy for social anxiety",
        "messages": [HumanMessage(content="Create a graded exposure hierarchy for social anxiety")]
    }
    
    for output in graph.stream(inputs):
        for key, value in output.items():
            print(f"\n--- Output from node '{key}' ---")
            if isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, str) and len(v) > 200:
                        print(f"  {k}: {v[:200]}...")
                    else:
                        print(f"  {k}: {v}")
            else:
                print(value)
    
    print("\n" + "=" * 60)
    print("Workflow Complete!")
