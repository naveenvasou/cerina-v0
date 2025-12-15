"""
Event Emitter for real-time streaming of agent events to WebSocket.
Uses asyncio Queue to decouple agent execution from WebSocket streaming.
"""
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    THOUGHT = "thought"
    THOUGHT_CHUNK = "thought_chunk"
    MESSAGE_CHUNK = "message_chunk"
    MESSAGE_END = "message_end"  # Signals end of a streaming message
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ARTIFACT = "artifact"
    STATUS = "status"
    MESSAGE = "message"
    AGENT_MEMORY = "agent_memory"
    AGENT_START = "agent_start"  # Agent starting execution
    # New event types for reflection loop
    CRITIQUE_DOCUMENT = "critique_document"  # Full critique for canvas display
    DRAFT_UPDATED = "draft_updated"          # Draft version update
    REFLECTION_STATUS = "reflection_status"  # Iteration progress update
    # Human-in-the-Loop event types
    PLAN_PENDING_APPROVAL = "plan_pending_approval"  # Workflow halted, awaiting user decision


@dataclass
class AgentEvent:
    """Represents a single event from an agent."""
    type: EventType
    agent: str
    content: str = ""
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None
    artifact_type: Optional[str] = None
    artifact_title: Optional[str] = None
    messages: Optional[list] = None  # For agent memory events
    scratchpad: Optional[str] = None  # For agent memory scratchpad
    # New fields for reflection loop
    iteration: Optional[int] = None   # Reflection iteration number
    version: Optional[int] = None     # Draft version number

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type.value,
            "agent": self.agent,
            "content": self.content,
        }
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_args:
            result["tool_args"] = self.tool_args
        if self.tool_output:
            result["tool_output"] = self.tool_output
        if self.artifact_type:
            result["artifact_type"] = self.artifact_type
        if self.artifact_title:
            result["artifact_title"] = self.artifact_title
        if self.messages is not None:
            result["messages"] = self.messages
        if self.scratchpad is not None:
            result["scratchpad"] = self.scratchpad
        if self.iteration is not None:
            result["iteration"] = self.iteration
        if self.version is not None:
            result["version"] = self.version
        return result


class EventEmitter:
    """
    Thread-safe event emitter using asyncio Queue.
    Agents push events synchronously, WebSocket consumes asynchronously.
    """
    
    def __init__(self):
        self._queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._closed: bool = False  # Flag to stop accepting events
    
    def initialize(self, loop: asyncio.AbstractEventLoop):
        """Initialize with the event loop (call from async context)."""
        self._loop = loop
        self._queue = asyncio.Queue()
        self._closed = False
    
    def close(self):
        """Mark emitter as closed. Future emit() calls will be no-ops."""
        self._closed = True
        self._queue = None
        self._loop = None
    
    def emit(self, event: AgentEvent):
        """Emit event if emitter is available and not closed."""
        
        # Skip if already closed (prevents stale events from background threads)
        if self._closed:
            return
        
        if self._queue is None or self._loop is None:
            return
        
        # Thread-safe way to put item in queue from sync context
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # Loop may be closed
            pass
    
    async def get(self) -> AgentEvent:
        """Get next event from queue (async)."""
        if self._queue is None:
            raise RuntimeError("EventEmitter not initialized")
        return await self._queue.get()
    
    def emit_thought(self, agent: str, content: str):
        """Convenience method for thought events."""
        self.emit(AgentEvent(type=EventType.THOUGHT, agent=agent, content=content))
    
    def emit_thought_chunk(self, agent: str, content: str):
        """Convenience method for streaming thought chunks."""
        self.emit(AgentEvent(type=EventType.THOUGHT_CHUNK, agent=agent, content=content))
    
    def emit_message_chunk(self, agent: str, content: str):
        """Convenience method for streaming message chunks."""
        self.emit(AgentEvent(type=EventType.MESSAGE_CHUNK, agent=agent, content=content))
    
    def emit_message_end(self, agent: str):
        """Signal end of a streaming message. Next message_chunk will start a new message."""
        self.emit(AgentEvent(type=EventType.MESSAGE_END, agent=agent, content=""))
    
    def emit_message(self, agent: str, content: str):
        """Convenience method for complete message events (for persistence)."""
        self.emit(AgentEvent(type=EventType.MESSAGE, agent=agent, content=content))
    
    def emit_tool_call(self, agent: str, tool_name: str, tool_args: Dict[str, Any]):
        """Convenience method for tool call events."""
        self.emit(AgentEvent(
            type=EventType.TOOL_CALL,
            agent=agent,
            content=f"Calling {tool_name}",
            tool_name=tool_name,
            tool_args=tool_args
        ))
    
    def emit_tool_result(self, agent: str, tool_name: str, tool_output: str, 
                         tool_args: Optional[Dict[str, Any]] = None):
        """Convenience method for tool result events.
        
        Args:
            agent: Agent name
            tool_name: Name of the tool that was called
            tool_output: Tool output/result
            tool_args: Optional tool arguments (so history has complete info)
        """
        self.emit(AgentEvent(
            type=EventType.TOOL_RESULT,
            agent=agent,
            content=f"Completed {tool_name}",
            tool_name=tool_name,
            tool_args=tool_args,
            tool_output=tool_output
        ))
    
    def emit_artifact(self, agent: str, content: str, artifact_type: str, title: str):
        """Convenience method for artifact events."""
        self.emit(AgentEvent(
            type=EventType.ARTIFACT,
            agent=agent,
            content=content,
            artifact_type=artifact_type,
            artifact_title=title
        ))
    
    def emit_status(self, agent: str, content: str):
        """Convenience method for status events."""
        self.emit(AgentEvent(type=EventType.STATUS, agent=agent, content=content))
    
    def emit_agent_start(self, agent: str, content: str):
        """Emit agent_start event when an agent begins execution."""
        print("EMITTING AGENT START EVENT :", agent, content)
        self.emit(AgentEvent(type=EventType.AGENT_START, agent=agent, content=content))
    
    def emit_agent_memory(self, agent: str, messages: list, scratchpad: str = ""):
        """Emit the agent's internal message history for Memory popup."""
        self.emit(AgentEvent(
            type=EventType.AGENT_MEMORY,
            agent=agent,
            content="",
            messages=messages,
            scratchpad=scratchpad
        ))
    
    def emit_critique_document(self, agent: str, content: str, iteration: int):
        """Emit a critique document for canvas display."""
        self.emit(AgentEvent(
            type=EventType.CRITIQUE_DOCUMENT,
            agent=agent,
            content=content,
            iteration=iteration
        ))
    
    def emit_draft_updated(self, agent: str, content: str, version: int):
        """Emit a draft version update."""
        self.emit(AgentEvent(
            type=EventType.DRAFT_UPDATED,
            agent=agent,
            content=content,
            version=version
        ))
    
    def emit_reflection_status(self, agent: str, iteration: int, max_iterations: int, approved: bool):
        """Emit reflection loop status update."""
        status = "approved" if approved else f"iteration {iteration}/{max_iterations}"
        self.emit(AgentEvent(
            type=EventType.REFLECTION_STATUS,
            agent=agent,
            content=status,
            iteration=iteration
        ))
    
    def emit_plan_pending_approval(self, agent: str, plan_json: str, user_preview: str):
        """Emit when workflow halts for user approval of the plan."""
        self.emit(AgentEvent(
            type=EventType.PLAN_PENDING_APPROVAL,
            agent=agent,
            content=plan_json,
            artifact_title=user_preview  # Reuse artifact_title for preview text
        ))
    
    def emit_done(self):
        """Signal that processing is complete."""
        self.emit(AgentEvent(type=EventType.STATUS, agent="system", content="__DONE__"))



# Global emitter instance (will be initialized per request)
# We use a context variable approach for thread safety, with a thread-safe 
# global fallback for cases where contextvars don't propagate (e.g., asyncio.to_thread)
import contextvars
import threading

_current_emitter: contextvars.ContextVar[Optional[EventEmitter]] = contextvars.ContextVar('emitter', default=None)

# Thread-safe global fallback for when context vars don't propagate
_global_emitter: Optional[EventEmitter] = None
_emitter_lock = threading.Lock()


def get_emitter() -> Optional[EventEmitter]:
    """Get the current request's emitter.
    
    First tries to get from context variable, then falls back to global reference.
    This handles cases where contextvars don't propagate to threads properly.
    """
    # Try context variable first (preferred)
    emitter = _current_emitter.get()
    if emitter is not None:
        return emitter
    
    # Fallback to global reference (for thread scenarios)
    global _global_emitter
    with _emitter_lock:
        return _global_emitter


def set_emitter(emitter: EventEmitter):
    """Set the current request's emitter.
    
    Sets both the context variable and the global fallback.
    """
    global _global_emitter
    _current_emitter.set(emitter)
    # Also set global fallback for thread scenarios
    with _emitter_lock:
        _global_emitter = emitter


def clear_emitter():
    """Clear the emitter references (call at end of request)."""
    global _global_emitter
    _current_emitter.set(None)
    with _emitter_lock:
        _global_emitter = None
