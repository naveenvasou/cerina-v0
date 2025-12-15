"""
Sessions REST API

CRUD operations for chat sessions.
All endpoints require authentication and filter by user_id.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from backend.database import get_session
from backend.models import Session, Message, Artifact, WorkflowRun, AgentEvent, AgentMemory, ChatHistoryItem
import json


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# --- Pydantic Schemas ---

class SessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None


class SessionResponse(BaseModel):
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    agent_name: str
    artifact_type: str
    title: str
    content: str
    version: int
    iteration: Optional[int]
    created_at: datetime
    
    class Config:
        from_attributes = True


class WorkflowRunResponse(BaseModel):
    id: str
    session_id: str
    user_query: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    final_route: Optional[str]
    reflection_iterations: int
    is_approved: bool
    
    class Config:
        from_attributes = True


class AgentEventResponse(BaseModel):
    id: str
    workflow_run_id: str
    agent_name: str
    event_type: str
    content: str
    tool_name: Optional[str]
    tool_args_json: Optional[str]
    tool_output: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class AgentMemoryResponse(BaseModel):
    id: str
    workflow_run_id: str
    agent_name: str
    messages_json: str
    scratchpad: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatHistoryItemResponse(BaseModel):
    """
    Response schema for chat history items.
    Designed to map directly to frontend Message type for easy rendering.
    """
    id: str
    sequence: int
    item_type: str  # Maps to frontend 'type' field
    role: str  # 'user', 'assistant', 'agent', 'system'
    content: str
    agent_name: Optional[str] = None
    
    # Tool fields
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None  # Parsed from JSON
    tool_output: Optional[str] = None
    tool_status: Optional[str] = None
    
    # Artifact fields
    artifact_type: Optional[str] = None
    artifact_title: Optional[str] = None
    
    # Reflection fields
    iteration: Optional[int] = None
    version: Optional[int] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


# --- Temporary: Get user_id from header (will be replaced with Firebase auth) ---

from fastapi import Header

def get_current_user_id(user_id: str = Header(..., alias="user-id", description="Firebase User UID")) -> str:
    """
    Temporary: Returns the user ID passed in the header.
    In production, this should verify the Firebase JWT token from Authorization header.
    """
    return user_id


# --- Endpoints ---

@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """List all sessions for the current user."""
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .where(Session.is_active == True)
        .order_by(Session.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SessionResponse)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Create a new session."""
    session = Session(
        user_id=user_id,
        title=body.title or "New Chat"
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session_by_id(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get a specific session by ID."""
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Update a session (e.g., rename title)."""
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if body.title is not None:
        session.title = body.title
    if body.is_active is not None:
        session.is_active = body.is_active
    session.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Soft delete a session (set is_active=False)."""
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.is_active = False
    session.updated_at = datetime.utcnow()
    await db.commit()
    
    return {"message": "Session deleted"}


@router.get("/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all messages for a session."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get messages
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{session_id}/artifacts", response_model=List[ArtifactResponse])
async def get_session_artifacts(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all artifacts for a session."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get artifacts
    result = await db.execute(
        select(Artifact)
        .where(Artifact.session_id == session_id)
        .order_by(Artifact.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}/workflow-runs", response_model=List[WorkflowRunResponse])
async def get_session_workflow_runs(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all workflow runs for a session."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get workflow runs
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.session_id == session_id)
        .order_by(WorkflowRun.started_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}/workflow-runs/{workflow_run_id}/events", response_model=List[AgentEventResponse])
async def get_workflow_run_events(
    session_id: str,
    workflow_run_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all agent events for a specific workflow run."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify workflow run belongs to session
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.id == workflow_run_id)
        .where(WorkflowRun.session_id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    # Get events
    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.workflow_run_id == workflow_run_id)
        .order_by(AgentEvent.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{session_id}/workflow-runs/{workflow_run_id}/memories", response_model=List[AgentMemoryResponse])
async def get_workflow_run_memories(
    session_id: str,
    workflow_run_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all agent memory snapshots for a specific workflow run."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify workflow run belongs to session
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.id == workflow_run_id)
        .where(WorkflowRun.session_id == session_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    # Get memories
    result = await db.execute(
        select(AgentMemory)
        .where(AgentMemory.workflow_run_id == workflow_run_id)
        .order_by(AgentMemory.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{session_id}/events", response_model=List[AgentEventResponse])
async def get_session_events(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """Get all agent events for a session (across all workflow runs)."""
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get all workflow run IDs for this session
    runs_result = await db.execute(
        select(WorkflowRun.id)
        .where(WorkflowRun.session_id == session_id)
    )
    run_ids = [r[0] for r in runs_result.fetchall()]
    
    if not run_ids:
        return []
    
    # Get all events for these workflow runs
    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.workflow_run_id.in_(run_ids))
        .order_by(AgentEvent.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{session_id}/chat-history", response_model=List[ChatHistoryItemResponse])
async def get_chat_history(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get the complete chat history for a session.
    
    Returns items in display order (by sequence), ready for frontend rendering.
    This is the SINGLE endpoint for loading chat UI state on page load/refresh.
    
    The response maps directly to the frontend Message type for easy rendering:
    - No complex reconstruction needed
    - Ordering is guaranteed by sequence number
    - All event types (messages, thoughts, tools, artifacts) in one response
    """
    # First verify session belongs to user
    result = await db.execute(
        select(Session)
        .where(Session.id == session_id)
        .where(Session.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get chat history ordered by sequence
    result = await db.execute(
        select(ChatHistoryItem)
        .where(ChatHistoryItem.session_id == session_id)
        .order_by(ChatHistoryItem.sequence.asc())
    )
    items = result.scalars().all()
    
    # Transform for response (parse JSON fields)
    response = []
    for item in items:
        response.append(ChatHistoryItemResponse(
            id=item.id,
            sequence=item.sequence,
            item_type=item.item_type,
            role=item.role,
            content=item.content,
            agent_name=item.agent_name,
            tool_name=item.tool_name,
            tool_args=json.loads(item.tool_args_json) if item.tool_args_json else None,
            tool_output=item.tool_output,
            tool_status=item.tool_status,
            artifact_type=item.artifact_type,
            artifact_title=item.artifact_title,
            iteration=item.iteration,
            version=item.version,
            created_at=item.created_at
        ))
    
    return response
