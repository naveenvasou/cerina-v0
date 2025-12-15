"""
Database Persistence Layer

Provides async helper functions for persisting:
- Messages (user/assistant)
- Workflow runs
- Agent events
- Artifacts (plans, drafts, critiques)
- Agent memory snapshots
- Chat history
- Session titles
"""

from datetime import datetime
from typing import Optional
import json

from sqlmodel import select, func
from backend.database import async_session_maker
from backend.models import (
    Session, Message, WorkflowRun,
    AgentEvent as AgentEventModel, Artifact, AgentMemory,
    ChatHistoryItem
)


async def save_message(
    session_id: str, 
    role: str, 
    content: str, 
    workflow_run_id: Optional[str] = None
) -> Optional[str]:
    """Save message to database. Returns message ID."""
    if not session_id or not async_session_maker:
        return None
    try:
        async with async_session_maker() as db:
            msg = Message(
                session_id=session_id,
                role=role,
                content=content,
                workflow_run_id=workflow_run_id
            )
            db.add(msg)
            await db.commit()
            await db.refresh(msg)
            return msg.id
    except Exception as e:
        print(f"Failed to save message: {e}")
        return None


async def create_workflow_run(session_id: str, user_query: str) -> Optional[str]:
    """Create a new workflow run record. Returns workflow_run_id."""
    if not session_id or not async_session_maker:
        return None
    try:
        async with async_session_maker() as db:
            run = WorkflowRun(
                session_id=session_id,
                user_query=user_query,
                status="running"
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            return run.id
    except Exception as e:
        print(f"Failed to create workflow run: {e}")
        return None


async def update_workflow_run(
    workflow_run_id: str, 
    status: str = "completed",
    final_route: Optional[str] = None,
    reflection_iterations: int = 0,
    is_approved: bool = False,
    hitl_pending: Optional[bool] = None,
    pending_plan_json: Optional[str] = None
):
    """Update workflow run status and metadata."""
    if not workflow_run_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                run.status = status
                run.completed_at = datetime.utcnow()
                if final_route:
                    run.final_route = final_route
                run.reflection_iterations = reflection_iterations
                run.is_approved = is_approved
                if hitl_pending is not None:
                    run.hitl_pending = hitl_pending
                if pending_plan_json is not None:
                    run.pending_plan_json = pending_plan_json
                db.add(run)
                await db.commit()
    except Exception as e:
        print(f"Failed to update workflow run: {e}")


async def set_hitl_pending(
    workflow_run_id: str,
    pending: bool,
    plan_json: Optional[str] = None
):
    """Set HITL pending approval state for a workflow run."""
    if not workflow_run_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(WorkflowRun).where(WorkflowRun.id == workflow_run_id)
            )
            run = result.scalar_one_or_none()
            if run:
                run.hitl_pending = pending
                if plan_json is not None:
                    run.pending_plan_json = plan_json
                elif not pending:
                    run.pending_plan_json = None  # Clear when no longer pending
                run.status = "awaiting_approval" if pending else run.status
                db.add(run)
                await db.commit()
    except Exception as e:
        print(f"Failed to set HITL pending: {e}")


async def save_agent_event(
    workflow_run_id: str,
    agent_name: str,
    event_type: str,
    content: str,
    tool_name: Optional[str] = None,
    tool_args_json: Optional[str] = None,
    tool_output: Optional[str] = None
):
    """Save an agent event to database."""
    if not workflow_run_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            event = AgentEventModel(
                workflow_run_id=workflow_run_id,
                agent_name=agent_name,
                event_type=event_type,
                content=content[:10000] if content else "",
                tool_name=tool_name,
                tool_args_json=tool_args_json,
                tool_output=tool_output[:5000] if tool_output else None
            )
            db.add(event)
            await db.commit()
    except Exception as e:
        print(f"Failed to save agent event: {e}")


async def save_artifact(
    workflow_run_id: str,
    session_id: str,
    agent_name: str,
    artifact_type: str,
    title: str,
    content: str,
    version: int = 1,
    iteration: Optional[int] = None
):
    """Save an artifact to database."""
    if not workflow_run_id or not session_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            artifact = Artifact(
                workflow_run_id=workflow_run_id,
                session_id=session_id,
                agent_name=agent_name,
                artifact_type=artifact_type,
                title=title,
                content=content,
                version=version,
                iteration=iteration
            )
            db.add(artifact)
            await db.commit()
    except Exception as e:
        print(f"Failed to save artifact: {e}")


async def save_agent_memory(
    workflow_run_id: str,
    agent_name: str,
    messages: list,
    scratchpad: str
):
    """Save agent memory snapshot to database."""
    if not workflow_run_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            memory = AgentMemory(
                workflow_run_id=workflow_run_id,
                agent_name=agent_name,
                messages_json=json.dumps(messages) if messages else "[]",
                scratchpad=scratchpad or ""
            )
            db.add(memory)
            await db.commit()
    except Exception as e:
        print(f"Failed to save agent memory: {e}")


async def update_session_title(session_id: str, user_query: str):
    """Update session title based on first user message (if still 'New Chat')."""
    if not session_id or not async_session_maker:
        return
    try:
        async with async_session_maker() as db:
            result = await db.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session and session.title == "New Chat":
                title = user_query[:50].strip()
                if len(user_query) > 50:
                    title += "..."
                session.title = title
                session.updated_at = datetime.utcnow()
                db.add(session)
                await db.commit()
    except Exception as e:
        print(f"Failed to update session title: {e}")


async def append_to_chat_history(
    session_id: str,
    item_type: str,
    role: str,
    content: str,
    workflow_run_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[dict] = None,
    tool_output: Optional[str] = None,
    tool_status: Optional[str] = None,
    artifact_type: Optional[str] = None,
    artifact_title: Optional[str] = None,
    iteration: Optional[int] = None,
    version: Optional[int] = None
) -> Optional[str]:
    """
    Append an item to the chat history.
    
    This is the SINGLE function that writes to chat_history table.
    Each item gets an auto-incrementing sequence number for ordering.
    
    Returns the generated item ID for WebSocket emission (for deduplication).
    
    NOTE: Streaming chunks (thought_chunk, message_chunk) should NOT be saved here.
    Only save final, complete messages.
    """
    if not session_id or not async_session_maker:
        return None
    
    try:
        async with async_session_maker() as db:
            # Get next sequence number for this session
            result = await db.execute(
                select(func.coalesce(func.max(ChatHistoryItem.sequence), 0))
                .where(ChatHistoryItem.session_id == session_id)
            )
            max_seq = result.scalar() or 0
            next_seq = max_seq + 1
            
            item = ChatHistoryItem(
                session_id=session_id,
                workflow_run_id=workflow_run_id,
                sequence=next_seq,
                item_type=item_type,
                role=role,
                content=content[:10000] if content else "",
                agent_name=agent_name,
                tool_name=tool_name,
                tool_args_json=json.dumps(tool_args) if tool_args else None,
                tool_output=tool_output[:5000] if tool_output else None,
                tool_status=tool_status,
                artifact_type=artifact_type,
                artifact_title=artifact_title,
                iteration=iteration,
                version=version
            )
            db.add(item)
            await db.commit()
            await db.refresh(item)
            return item.id
    except Exception as e:
        print(f"Failed to append to chat history: {e}")
        return None
