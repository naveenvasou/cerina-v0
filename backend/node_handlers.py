"""
Graph Node Event Handlers

Handles processing of state updates from each graph node:
- Router: Classify intent, respond to conversations
- Planner: Save clinical plan artifact
- Draftsman: Save initial draft artifact
- Critic: Save critique, track approval status
- Reviser: Save revised draft versions
- Synthesizer: Save final CBT exercise
"""

from typing import Optional, Tuple
import json

from fastapi import WebSocket
from backend.persistence import save_message, save_artifact, append_to_chat_history


async def handle_router(
    state_update: dict,
    session_id: str,
    workflow_run_id: str,
    websocket: WebSocket
) -> str:
    """
    Handle router node output.
    
    Returns the route classification for workflow tracking.
    Sends conversation responses directly to WebSocket.
    """
    route = state_update.get("route", "")
    router_response = state_update.get("router_response", "")
    
    if route == "conversation" and router_response:
        # Save assistant message
        await save_message(session_id, "assistant", router_response, workflow_run_id)
        
        # Save to ChatHistory for reload
        chat_id = await append_to_chat_history(
            session_id=session_id,
            workflow_run_id=workflow_run_id,
            item_type="message",
            role="assistant",
            content=router_response,
            agent_name="Cerina"
        )
        
        await websocket.send_json({
            "type": "message",
            "agent": "Cerina",
            "content": router_response,
            "id": chat_id
        })
    
    return route


async def handle_planner(
    state_update: dict,
    session_id: str,
    workflow_run_id: str
) -> None:
    """Handle planner node output - saves plan artifact."""
    plan_content = state_update.get("plan", "")
    if plan_content:
        await save_artifact(
            workflow_run_id, session_id,
            "planner", "plan", "Clinical Plan",
            plan_content if isinstance(plan_content, str) else json.dumps(plan_content)
        )


async def handle_draftsman(
    state_update: dict,
    session_id: str,
    workflow_run_id: str
) -> None:
    """Handle draftsman node output - saves initial draft artifact."""
    draft_content = state_update.get("current_draft", "") or state_update.get("draft", "")
    if draft_content:
        await save_artifact(
            workflow_run_id, session_id,
            "draftsman", "draft", "CBT Exercise Draft",
            draft_content, version=1
        )


async def handle_critic(
    state_update: dict,
    session_id: str,
    workflow_run_id: str
) -> Tuple[int, bool]:
    """
    Handle critic node output.
    
    Returns (reflection_iteration, critique_approved) for workflow tracking.
    """
    critique_approved = state_update.get("critique_approved", False)
    reflection_iteration = state_update.get("reflection_iteration", 1)
    
    critique_doc = state_update.get("critique_document", "")
    if critique_doc:
        await save_artifact(
            workflow_run_id, session_id,
            "critic", "critique", f"Critique (Iteration {reflection_iteration})",
            critique_doc, iteration=reflection_iteration
        )
    
    return reflection_iteration, critique_approved


async def handle_reviser(
    state_update: dict,
    session_id: str,
    workflow_run_id: str
) -> None:
    """Handle reviser node output - saves revised draft artifact."""
    reflection_iteration = state_update.get("reflection_iteration", 1)
    revised_draft = state_update.get("current_draft", "")
    
    if revised_draft:
        await save_artifact(
            workflow_run_id, session_id,
            "reviser", "draft_revision", f"Revised Draft (v{reflection_iteration})",
            revised_draft, version=reflection_iteration, iteration=reflection_iteration
        )


async def handle_synthesizer(
    state_update: dict,
    session_id: str,
    workflow_run_id: str,
    websocket: WebSocket
) -> None:
    """Handle synthesizer node output - saves final CBT exercise and sends completion."""
    final_output = state_update.get("final_presentation", "")
    
    if final_output:
        await save_artifact(
            workflow_run_id, session_id,
            "synthesizer", "cbt_exercise", "Final CBT Exercise",
            final_output
        )
        
        # Save to ChatHistory for reload
        await append_to_chat_history(
            session_id=session_id,
            workflow_run_id=workflow_run_id,
            item_type="artifact",
            role="agent",
            content=final_output,
            agent_name="synthesizer",
            artifact_type="cbt_exercise",
            artifact_title="Final CBT Exercise"
        )
    
    await websocket.send_json({
        "type": "status",
        "agent": "System",
        "content": "Complete."
    })


async def handle_respond(websocket: WebSocket) -> None:
    """Handle respond node - sends completion status."""
    await websocket.send_json({
        "type": "status",
        "agent": "System",
        "content": "Complete."
    })
