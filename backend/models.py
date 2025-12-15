"""
SQLModel Database Models

Comprehensive schema for Cerina CBT Agent application.
Supports session management, workflow tracking, and agent event logging.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

from backend.utils.id_generator import (
    generate_session_id,
    generate_workflow_run_id,
    generate_message_id,
    generate_artifact_id,
    generate_event_id,
    generate_memory_id,
    generate_chat_history_id
)


class Session(SQLModel, table=True):
    """
    A conversation thread (like ChatGPT conversation).
    
    Each user can have multiple sessions, each containing
    multiple workflow runs and messages.
    """
    __tablename__ = "sessions"
    
    id: str = Field(default_factory=generate_session_id, primary_key=True)
    user_id: str = Field(index=True)  # Firebase UID
    title: str = Field(default="New Chat", max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True)


class WorkflowRun(SQLModel, table=True):
    """
    A single workflow execution within a session.
    
    Created each time a user sends a query that triggers the LangGraph workflow.
    Tracks status for resumption of interrupted workflows.
    """
    __tablename__ = "workflow_runs"
    
    id: str = Field(default_factory=generate_workflow_run_id, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    user_query: str  # The user's input that triggered this run
    status: str = Field(default="running")  # running, completed, interrupted, failed
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    
    # Workflow metadata
    final_route: Optional[str] = Field(default=None)  # conversation, planner, draftsman
    reflection_iterations: int = Field(default=0)
    is_approved: bool = Field(default=False)
    
    # HITL (Human-in-the-Loop) state
    hitl_pending: bool = Field(default=False)  # True when waiting for user approval
    pending_plan_json: Optional[str] = Field(default=None)  # The plan awaiting approval


class Message(SQLModel, table=True):
    """
    Chat messages displayed in the sidebar.
    
    Stores user queries and consolidated agent responses.
    For detailed agent activity, see AgentEvent.
    """
    __tablename__ = "messages"
    
    id: str = Field(default_factory=generate_message_id, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    workflow_run_id: Optional[str] = Field(default=None, foreign_key="workflow_runs.id")
    role: str  # 'user', 'assistant'
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentEvent(SQLModel, table=True):
    """
    Detailed agent activity log.
    
    Records every thought, message chunk, tool call, and status update
    from each agent. Enables "which agent said what?" queries.
    """
    __tablename__ = "agent_events"
    
    id: str = Field(default_factory=generate_event_id, primary_key=True)
    workflow_run_id: str = Field(foreign_key="workflow_runs.id", index=True)
    agent_name: str  # router, planner, draftsman, critic, reviser, synthesizer
    event_type: str  # thought, message_chunk, tool_call, tool_result, status, artifact
    content: str
    
    # Optional fields based on event_type
    tool_name: Optional[str] = Field(default=None)
    tool_args_json: Optional[str] = Field(default=None)  # JSON string
    tool_output: Optional[str] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Artifact(SQLModel, table=True):
    """
    Generated documents (plans, drafts, critiques, final exercises).
    
    Tracks version history and which agent/iteration produced each artifact.
    """
    __tablename__ = "artifacts"
    
    id: str = Field(default_factory=generate_artifact_id, primary_key=True)
    workflow_run_id: str = Field(foreign_key="workflow_runs.id", index=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    agent_name: str  # Which agent created this
    artifact_type: str  # plan, draft, critique, draft_revision, cbt_exercise
    title: str
    content: str
    version: int = Field(default=1)
    iteration: Optional[int] = Field(default=None)  # For critique/revision loop tracking
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentMemory(SQLModel, table=True):
    """
    Agent internal state snapshots (for Memory popup).
    
    Stores the messages and scratchpad content that agents emit
    for transparency and debugging.
    """
    __tablename__ = "agent_memories"
    
    id: str = Field(default_factory=generate_memory_id, primary_key=True)
    workflow_run_id: str = Field(foreign_key="workflow_runs.id", index=True)
    agent_name: str
    messages_json: str  # JSON array of message history
    scratchpad: str  # Reasoning/thinking content
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatHistoryItem(SQLModel, table=True):
    """
    Unified timeline of everything displayed in the chat interface.
    This is the single source of truth for chat UI rendering.
    
    Each row = one item the user sees in the chat sidebar.
    The schema directly mirrors the frontend Message type for easy serialization.
    
    NOTE: Streaming chunks (thought_chunk, message_chunk) are NOT stored here.
    Only final, complete messages are persisted. Chunks are streamed directly
    via WebSocket and discarded.
    """
    __tablename__ = "chat_history"
    
    id: str = Field(default_factory=generate_chat_history_id, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id", index=True)
    workflow_run_id: Optional[str] = Field(default=None, foreign_key="workflow_runs.id")
    
    # Ordering: sequence number per session (auto-assigned in append function)
    sequence: int = Field(index=True)
    
    # --- Core Fields (match frontend Message type) ---
    item_type: str  # 'user_message', 'assistant_message', 'thought', 'tool_call', 
                    # 'tool_result', 'artifact', 'agent_start', 'status', 'critique'
    role: str  # 'user', 'assistant', 'agent', 'system'
    content: str
    agent_name: Optional[str] = Field(default=None)
    
    # --- Tool-specific fields ---
    tool_name: Optional[str] = Field(default=None)
    tool_args_json: Optional[str] = Field(default=None)
    tool_output: Optional[str] = Field(default=None)
    tool_status: Optional[str] = Field(default=None)  # 'running', 'completed'
    
    # --- Artifact-specific fields ---
    artifact_type: Optional[str] = Field(default=None)
    artifact_title: Optional[str] = Field(default=None)
    
    # --- Reflection loop fields ---
    iteration: Optional[int] = Field(default=None)
    version: Optional[int] = Field(default=None)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
