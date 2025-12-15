"""
WebSocket Routes

Handles WebSocket connections for real-time chat communication.
Delegates to:
- persistence.py for database operations
- node_handlers.py for graph node event processing
"""

from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from backend.graph import get_compiled_graph
from backend.events import EventEmitter, set_emitter, EventType
from backend.utils.id_generator import generate_workflow_run_id, generate_session_id
from langgraph.types import Command  # For resuming interrupted graphs
from backend.database import async_session_maker
from backend.models import Session
from backend.persistence import (
    save_message,
    create_workflow_run,
    update_workflow_run,
    save_agent_event,
    save_artifact,
    save_agent_memory,
    update_session_title,
    append_to_chat_history,
    set_hitl_pending
)
from backend.node_handlers import (
    handle_router,
    handle_planner,
    handle_draftsman,
    handle_critic,
    handle_reviser,
    handle_synthesizer,
    handle_respond
)
import asyncio
import json
from typing import Optional

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None)
):
    await websocket.accept()
    
    # Establish session context
    current_session_id = session_id
    is_first_message = True
    
    # Create new session if needed
    if not current_session_id and user_id and async_session_maker:
        try:
            async with async_session_maker() as db:
                new_session_id = generate_session_id()
                session = Session(id=new_session_id, user_id=user_id, title="New Chat")
                db.add(session)
                await db.commit()
                current_session_id = new_session_id
                
                await websocket.send_json({
                    "type": "session_created",
                    "session_id": current_session_id,
                    "title": "New Chat"
                })
        except Exception as e:
            print(f"Error creating session: {e}")
    
    # Fallback to ephemeral ID
    if not current_session_id:
        current_session_id = generate_workflow_run_id()
    
    # Track running workflow tasks for stop functionality
    running_task: Optional[asyncio.Task] = None
    consumer_task: Optional[asyncio.Task] = None
    current_workflow_run_id: Optional[str] = None  # Track for resume
    
    # Check if session has a pending checkpoint (can be resumed)
    thread_config = {"configurable": {"thread_id": current_session_id}}
    try:
        compiled_graph = get_compiled_graph()
        state = await compiled_graph.aget_state(thread_config)
        if state and state.next:
            pending_nodes = list(state.next) if state.next else []
            
            # If pending at HITL approval node, don't show Resume button
            # The approval modal handles that case instead
            is_hitl_pending = "await_plan_approval" in pending_nodes
            
            # Send workflow_status to frontend
            await websocket.send_json({
                "type": "workflow_status",
                "running": False,
                "canResume": not is_hitl_pending,  # Only resumable if NOT at HITL node
                "pendingNodes": pending_nodes
            })
            print(f"📋 Session {current_session_id} has pending checkpoint at: {state.next}")
            if is_hitl_pending:
                print("   (HITL approval pending - handled by approval modal)")
    except Exception as e:
        print(f"Could not check checkpoint status: {e}")
    
    try:
        while True:
            # Wait for user input
            data = await websocket.receive_text()
            
            # Parse message
            try:
                message_data = json.loads(data)
                message_type = message_data.get("type", "chat_message")
                user_query = message_data.get("message", data)
                session_id = message_data.get("session_id", session_id)
            except json.JSONDecodeError:
                message_type = "chat_message"
                user_query = data
            
            # Handle HITL plan decision (resume interrupted graph)
            if message_type == "plan_decision":
                decision = message_data.get("decision", "rejected")
                feedback = message_data.get("feedback", "")
                workflow_run_id = message_data.get("workflow_run_id")
                
                print(f"📋 HITL Decision received: {decision}")
                if feedback:
                    print(f"   Feedback: {feedback[:100]}..." if len(feedback) > 100 else f"   Feedback: {feedback}")
                
                # PERSISTENCE: Save the decision/feedback to chat history
                if decision == "revised" and feedback:
                    # Save user's revision request as a user message
                    await append_to_chat_history(
                        session_id=current_session_id,
                        workflow_run_id=workflow_run_id,
                        item_type="message",
                        role="user",
                        content=feedback
                    )
                    # Also send to WebSocket so frontend can display immediately
                    await websocket.send_json({
                        "type": "user_message",
                        "content": feedback,
                        "timestamp": datetime.now().isoformat()
                    })
                elif decision == "approved":
                    await append_to_chat_history(
                        session_id=current_session_id,
                        workflow_run_id=workflow_run_id,
                        item_type="log",
                        role="system",
                        content="Plan approved by user"
                    )
                elif decision == "rejected":
                    await append_to_chat_history(
                        session_id=current_session_id,
                        workflow_run_id=workflow_run_id,
                        item_type="log",
                        role="system",
                        content="Plan rejected by user"
                    )
                
                # Clear HITL pending state
                await set_hitl_pending(workflow_run_id, pending=False)
                
                # Create event emitter for resume
                emitter = EventEmitter()
                emitter.initialize(asyncio.get_running_loop())
                set_emitter(emitter)
                
                thread_config = {"configurable": {"thread_id": current_session_id}}
                
                # Resume the interrupted graph with user's decision
                resume_value = {"decision": decision, "feedback": feedback}
                
                async def run_resumed_graph():
                    compiled_graph = get_compiled_graph()
                    try:
                        async for event in compiled_graph.astream(
                            Command(resume=resume_value),
                            config=thread_config
                        ):
                            for node_name, state_update in event.items():
                                # Handle all nodes as in normal flow
                                if node_name == "draftsman":
                                    await handle_draftsman(
                                        state_update, current_session_id, workflow_run_id
                                    )
                                elif node_name == "critic":
                                    await handle_critic(
                                        state_update, current_session_id, workflow_run_id
                                    )
                                elif node_name == "reviser":
                                    await handle_reviser(
                                        state_update, current_session_id, workflow_run_id
                                    )
                                elif node_name == "synthesizer":
                                    await handle_synthesizer(
                                        state_update, current_session_id,
                                        workflow_run_id, websocket
                                    )
                                elif node_name == "planner":
                                    # Planner re-run for revision
                                    await handle_planner(
                                        state_update, current_session_id, workflow_run_id
                                    )
                    finally:
                        # Check if the graph is truly completed or just interrupted again
                        # (e.g., if user requested revision and planner paused for approval again)
                        try:
                            state = await compiled_graph.aget_state(thread_config)
                            is_done = not bool(state.next)
                        except Exception:
                            # Fallback if aget_state fails
                            is_done = True
                            
                        if is_done:
                            status = "completed" if decision == "approved" else (
                                "revision_requested" if decision == "revised" else "rejected"
                            )
                            await update_workflow_run(workflow_run_id, status=status)
                            emitter.emit_done()
                        else:
                            # Interrupted again - do not emit done
                            pass
                
                async def stream_resumed_events():
                    import threading
                    print(f"DTO DEBUG: Stream Consumer running in Thread: {threading.get_ident()}")
                    print(f"DTO DEBUG: Stream Consumer Emitter ID: {id(emitter)}")
                    try:
                        while True:
                            event = await asyncio.wait_for(emitter.get(), timeout=120)
                            if event.type == EventType.STATUS and event.content == "__DONE__":
                                break
                            
                            print(f"DTO DEBUG: CONSUMER RECEIVED EVENT: {event.type} from {event.agent}")
                            
                            # PERSISTENCE: Save events to database (same as main loop)
                            if event.type == EventType.AGENT_MEMORY:
                                await save_agent_memory(
                                    workflow_run_id=workflow_run_id,
                                    agent_name=event.agent,
                                    messages=event.messages or [],
                                    scratchpad=event.scratchpad or ""
                                )
                            
                            if event.type == EventType.ARTIFACT:
                                await save_artifact(
                                    workflow_run_id=workflow_run_id,
                                    session_id=current_session_id,
                                    agent_name=event.agent,
                                    artifact_type=event.artifact_type or "unknown",
                                    title=event.artifact_title or "Untitled",
                                    content=event.content
                                )
                        
                            
                            # HITL: Persist pending approval state (handling revision loops)
                            if event.type == EventType.PLAN_PENDING_APPROVAL:
                                # When resuming after any decision, the node function re-runs and
                                # emits this event spuriously. We only care about NEW plans.
                                # For "approved" or "rejected" - skip entirely (no new plan)
                                # For "revised" - this is the NEW revised plan, so process it
                                if decision == "approved" or decision == "rejected":
                                    continue  # Skip this spurious event, keep consuming
                                
                                # For "revised" - this is a new plan needing approval
                                await set_hitl_pending(
                                    workflow_run_id=workflow_run_id,
                                    pending=True,
                                    plan_json=event.content
                                )
                                # Save log message
                                await append_to_chat_history(
                                    session_id=current_session_id,
                                    workflow_run_id=workflow_run_id,
                                    item_type="log",
                                    role="system",
                                    content="Revised plan ready for review. Waiting for user approval."
                                )
                                
                                # CRITICAL: Send to WebSocket so frontend shows UI immediately!
                                await websocket.send_json(event.to_dict())

                                break # Graceful exit for HITL (only when waiting for new approval)
                            
                            # Chat history persistence
                            should_save_to_history = event.type not in [
                                EventType.THOUGHT_CHUNK,
                                EventType.MESSAGE_CHUNK,
                                EventType.MESSAGE_END,
                                EventType.AGENT_MEMORY,
                                EventType.STATUS,
                                EventType.REFLECTION_STATUS,
                                EventType.TOOL_CALL
                            ]
                            
                            if should_save_to_history:
                                item_type = event.type.value
                                
                                if event.type == EventType.MESSAGE:
                                    role = "assistant"
                                elif event.type in [
                                    EventType.THOUGHT, EventType.TOOL_RESULT,
                                    EventType.AGENT_START, EventType.ARTIFACT,
                                    EventType.CRITIQUE_DOCUMENT, EventType.DRAFT_UPDATED
                                ]:
                                    role = "agent"
                                else:
                                    role = "system"
                                
                                await append_to_chat_history(
                                    session_id=current_session_id,
                                    workflow_run_id=workflow_run_id,
                                    item_type=item_type,
                                    role=role,
                                    content=event.content,
                                    agent_name=event.agent,
                                    tool_name=event.tool_name,
                                    tool_args=event.tool_args,
                                    tool_output=event.tool_output,
                                    artifact_type=event.artifact_type,
                                    artifact_title=event.artifact_title,
                                    iteration=event.iteration,
                                    version=event.version
                                )
                            
                            # Send to frontend (exclude MESSAGE and THOUGHT - they're for persistence only)
                            # Real-time display uses chunks (MESSAGE_CHUNK, THOUGHT_CHUNK)
                            should_send_to_websocket = event.type not in [
                                EventType.MESSAGE,
                                EventType.THOUGHT
                            ]
                            
                            if should_send_to_websocket:
                                await websocket.send_json(event.to_dict())
                            
                    except asyncio.TimeoutError:
                        print("Resume stream timeout")
                    except Exception as e:
                        print(f"Resume streaming error: {e}")
                
                # Ensure consumer starts by creating task explicitly
                consumer_task = asyncio.create_task(stream_resumed_events())
                # Yield to let it start
                await asyncio.sleep(0.1)
                
                try:
                     await run_resumed_graph()
                finally:
                     # Wait for consumer to finish (it waits for DONE signal)
                     await consumer_task
                continue  # Go back to waiting for next message
            
            # ============================================================
            # STOP WORKFLOW: Cancel both running and consumer tasks
            # ============================================================
            if message_type == "stop_workflow":
                print("🛑 Stop workflow requested")
                
                # Cancel both tasks
                if running_task and not running_task.done():
                    running_task.cancel()
                    try:
                        await running_task
                    except asyncio.CancelledError:
                        pass
                
                if consumer_task and not consumer_task.done():
                    consumer_task.cancel()
                    try:
                        await consumer_task
                    except asyncio.CancelledError:
                        pass
                
                print("✅ Workflow stopped - state preserved in checkpoint")
                
                # Check if stopped at HITL node (approval modal handles that)
                try:
                    compiled_graph = get_compiled_graph()
                    state = await compiled_graph.aget_state(thread_config)
                    if state and state.next:
                        pending_nodes = list(state.next)
                        is_hitl = "await_plan_approval" in pending_nodes
                        can_resume = not is_hitl
                    else:
                        can_resume = True  # Stopped mid-execution, should be resumable
                except Exception:
                    can_resume = True  # Default to resumable on error
                
                await websocket.send_json({
                    "type": "workflow_status",
                    "running": False,
                    "canResume": can_resume,
                    "message": "Workflow stopped. You can resume anytime."
                })
                continue
            
            # ============================================================
            # RESUME WORKFLOW: Continue from last checkpoint
            # ============================================================
            if message_type == "resume_workflow":
                print("▶️ Resume workflow requested")
                
                # Create event emitter for resume
                emitter = EventEmitter()
                emitter.initialize(asyncio.get_running_loop())
                set_emitter(emitter)
                
                thread_config = {"configurable": {"thread_id": current_session_id}}
                
                # Check if there's a pending checkpoint
                compiled_graph = get_compiled_graph()
                try:
                    state = await compiled_graph.aget_state(thread_config)
                    if not state or not state.next:
                        await websocket.send_json({
                            "type": "workflow_status",
                            "running": False,
                            "canResume": False,
                            "message": "No checkpoint to resume from."
                        })
                        continue
                except Exception as e:
                    print(f"Error checking state: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to check checkpoint: {str(e)}"
                    })
                    continue
                
                print(f"📋 Resuming from checkpoint at: {state.next}")
                
                # Send running status
                await websocket.send_json({
                    "type": "workflow_status",
                    "running": True,
                    "canResume": False
                })
                
                # Use tracked workflow_run_id or fallback to message/generate
                workflow_run_id = current_workflow_run_id or message_data.get("workflow_run_id") or generate_workflow_run_id()
                
                async def run_resumed_from_checkpoint():
                    try:
                        # Resume with None input - continues from checkpoint
                        async for event in compiled_graph.astream(None, config=thread_config):
                            for node_name, state_update in event.items():
                                if node_name == "router":
                                    await handle_router(state_update, current_session_id, workflow_run_id, websocket)
                                elif node_name == "planner":
                                    await handle_planner(state_update, current_session_id, workflow_run_id)
                                elif node_name == "draftsman":
                                    await handle_draftsman(state_update, current_session_id, workflow_run_id)
                                elif node_name == "critic":
                                    await handle_critic(state_update, current_session_id, workflow_run_id)
                                elif node_name == "reviser":
                                    await handle_reviser(state_update, current_session_id, workflow_run_id)
                                elif node_name == "synthesizer":
                                    await handle_synthesizer(state_update, current_session_id, workflow_run_id, websocket)
                    finally:
                        # Check if truly completed or interrupted again
                        try:
                            final_state = await compiled_graph.aget_state(thread_config)
                            is_done = not bool(final_state.next)
                        except Exception:
                            is_done = True
                        
                        if is_done:
                            await update_workflow_run(workflow_run_id, status="completed")
                            emitter.emit_done()
                        # If not done (e.g., hit another HITL interrupt), don't emit done
                
                async def stream_resume_events():
                    """Stream events with full persistence (same as main stream_events)."""
                    try:
                        while True:
                            event = await asyncio.wait_for(emitter.get(), timeout=120)
                            if event.type == EventType.STATUS and event.content == "__DONE__":
                                break
                            
                            # PERSISTENCE: Save events to database (Bug #5 fix)
                            if event.type == EventType.AGENT_MEMORY:
                                await save_agent_memory(
                                    workflow_run_id=workflow_run_id,
                                    agent_name=event.agent,
                                    messages=event.messages or [],
                                    scratchpad=event.scratchpad or ""
                                )
                            
                            if event.type == EventType.ARTIFACT:
                                await save_artifact(
                                    workflow_run_id=workflow_run_id,
                                    session_id=current_session_id,
                                    agent_name=event.agent,
                                    artifact_type=event.artifact_type or "unknown",
                                    title=event.artifact_title or "Untitled",
                                    content=event.content
                                )
                            
                            # Chat history persistence (same logic as main stream_events)
                            should_save_to_history = event.type not in [
                                EventType.THOUGHT_CHUNK,
                                EventType.MESSAGE_CHUNK,
                                EventType.MESSAGE_END,
                                EventType.AGENT_MEMORY,
                                EventType.STATUS,
                                EventType.REFLECTION_STATUS,
                                EventType.TOOL_CALL
                            ]
                            
                            if should_save_to_history:
                                item_type = event.type.value
                                
                                if event.type == EventType.MESSAGE:
                                    role = "assistant"
                                elif event.type in [
                                    EventType.THOUGHT, EventType.TOOL_RESULT,
                                    EventType.AGENT_START, EventType.ARTIFACT,
                                    EventType.CRITIQUE_DOCUMENT, EventType.DRAFT_UPDATED
                                ]:
                                    role = "agent"
                                else:
                                    role = "system"
                                
                                await append_to_chat_history(
                                    session_id=current_session_id,
                                    workflow_run_id=workflow_run_id,
                                    item_type=item_type,
                                    role=role,
                                    content=event.content,
                                    agent_name=event.agent,
                                    tool_name=event.tool_name,
                                    tool_args=event.tool_args,
                                    tool_output=event.tool_output,
                                    artifact_type=event.artifact_type,
                                    artifact_title=event.artifact_title,
                                    iteration=event.iteration,
                                    version=event.version
                                )
                            
                            # Handle HITL interrupt during resume
                            if event.type == EventType.PLAN_PENDING_APPROVAL:
                                await set_hitl_pending(
                                    workflow_run_id=workflow_run_id,
                                    pending=True,
                                    plan_json=event.content
                                )
                                await websocket.send_json(event.to_dict())
                                break
                            
                            # Send to frontend (exclude MESSAGE and THOUGHT - they're for persistence only)
                            should_send_to_websocket = event.type not in [
                                EventType.MESSAGE,
                                EventType.THOUGHT
                            ]
                            
                            if should_send_to_websocket:
                                await websocket.send_json(event.to_dict())
                            
                    except asyncio.TimeoutError:
                        print("Resume stream timeout")
                    except asyncio.CancelledError:
                        print("🛑 Resume stream cancelled")
                    except Exception as e:
                        print(f"Resume streaming error: {e}")
                
                consumer_task = asyncio.create_task(stream_resume_events())
                await asyncio.sleep(0.1)
                
                running_task = asyncio.create_task(run_resumed_from_checkpoint())
                try:
                    await running_task
                finally:
                    await consumer_task
                    # Check actual checkpoint state for canResume (Bug #2 fix)
                    try:
                        final_state = await compiled_graph.aget_state(thread_config)
                        if final_state and final_state.next:
                            pending_nodes = list(final_state.next)
                            # Don't show Resume if at HITL node (approval modal handles it)
                            is_hitl = "await_plan_approval" in pending_nodes
                            can_resume = not is_hitl
                        else:
                            can_resume = False
                    except Exception:
                        can_resume = False
                    
                    await websocket.send_json({
                        "type": "workflow_status",
                        "running": False,
                        "canResume": can_resume
                    })
                continue
            
            # Create workflow run
            workflow_run_id = await create_workflow_run(current_session_id, user_query)
            if not workflow_run_id:
                workflow_run_id = generate_workflow_run_id()
            
            # Track for resume operations
            current_workflow_run_id = workflow_run_id
            
            # Save user message
            await save_message(current_session_id, "user", user_query, workflow_run_id)
            await append_to_chat_history(
                session_id=current_session_id,
                item_type="user_message",
                role="user",
                content=user_query,
                workflow_run_id=workflow_run_id
            )
            
            # Update session title on first message
            if is_first_message:
                await update_session_title(current_session_id, user_query)
                is_first_message = False
            
            # Create event emitter
            emitter = EventEmitter()
            emitter.initialize(asyncio.get_running_loop())
            set_emitter(emitter)
            
            # Thread config for checkpointing
            thread_config = {"configurable": {"thread_id": current_session_id}}
            
            # Initial state
            inputs = {
                "user_query": user_query,
                "route": None,
                "router_response": None,
                "plan": None,
                "draft": None,
                "planner_trace": None
            }
            
            # Track state for workflow completion
            final_route = None
            reflection_iterations = 0
            is_approved = False
            
            async def run_graph():
                nonlocal final_route, reflection_iterations, is_approved
                compiled_graph = get_compiled_graph()
                try:
                    async for event in compiled_graph.astream(inputs, config=thread_config):
                        for node_name, state_update in event.items():
                            if node_name == "router":
                                final_route = await handle_router(
                                    state_update, current_session_id, 
                                    workflow_run_id, websocket
                                )
                            elif node_name == "respond":
                                await handle_respond(websocket)
                            elif node_name == "planner":
                                await handle_planner(
                                    state_update, current_session_id, workflow_run_id
                                )
                            elif node_name == "draftsman":
                                await handle_draftsman(
                                    state_update, current_session_id, workflow_run_id
                                )
                            elif node_name == "critic":
                                reflection_iterations, is_approved = await handle_critic(
                                    state_update, current_session_id, workflow_run_id
                                )
                            elif node_name == "reviser":
                                await handle_reviser(
                                    state_update, current_session_id, workflow_run_id
                                )
                            elif node_name == "synthesizer":
                                await handle_synthesizer(
                                    state_update, current_session_id,
                                    workflow_run_id, websocket
                                )
                finally:
                    # Update workflow run status if complete
                    if final_route: # Only if we completed execution (not interrupted)
                        await update_workflow_run(
                            workflow_run_id,
                            status="completed",
                            final_route=final_route,
                            reflection_iterations=reflection_iterations,
                            is_approved=is_approved
                        )
                        emitter.emit_done()
                    else:
                        # Interrupted for HITL - DO NOT emit done!
                        # The graph is just paused. If we emit done, the event stream loop exits
                        # and pending events in the queue won't be processed/saved.
                        pass
            
            async def stream_events():
                try:
                    while True:
                        event = await asyncio.wait_for(emitter.get(), timeout=120)
                        
                        # Check for done signal
                        if event.type == EventType.STATUS and event.content == "__DONE__":
                            break
                        
                        # Persist to AgentEvents table
                        await save_agent_event(
                            workflow_run_id=workflow_run_id,
                            agent_name=event.agent,
                            event_type=event.type.value,
                            content=event.content,
                            tool_name=event.tool_name,
                            tool_args_json=json.dumps(event.tool_args) if event.tool_args else None,
                            tool_output=event.tool_output
                        )
                        
                        # Handle special events
                        if event.type == EventType.AGENT_MEMORY:
                            await save_agent_memory(
                                workflow_run_id=workflow_run_id,
                                agent_name=event.agent,
                                messages=event.messages or [],
                                scratchpad=event.scratchpad or ""
                            )
                        
                        if event.type == EventType.ARTIFACT:
                            await save_artifact(
                                workflow_run_id=workflow_run_id,
                                session_id=current_session_id,
                                agent_name=event.agent,
                                artifact_type=event.artifact_type or "unknown",
                                title=event.artifact_title or "Untitled",
                                content=event.content
                            )
                        
                            # HITL: Persist pending approval state
                        if event.type == EventType.PLAN_PENDING_APPROVAL:
                            await set_hitl_pending(
                                workflow_run_id=workflow_run_id,
                                pending=True,
                                plan_json=event.content  # The plan JSON
                            )
                            
                            # Save this event to chat history so it appears in the log
                            await append_to_chat_history(
                                session_id=current_session_id,
                                workflow_run_id=workflow_run_id,
                                item_type="log",
                                role="system",
                                content="Plan ready for review. Waiting for user approval."
                            )

                            # CRITICAL: Send to WebSocket so frontend shows UI immediately!
                            # We break the loop below, so the normal "should_send_to_websocket" logic is skipped.
                            await websocket.send_json(event.to_dict())
                            
                            # CRITICAL: Break the stream loop here!
                            break
                        
                        # Chat history persistence
                        chat_history_id = None
                        should_save_to_history = event.type not in [
                            EventType.THOUGHT_CHUNK,
                            EventType.MESSAGE_CHUNK,
                            EventType.MESSAGE_END,
                            EventType.AGENT_MEMORY,
                            EventType.STATUS,
                            EventType.REFLECTION_STATUS,
                            EventType.TOOL_CALL
                        ]
                        
                        if should_save_to_history:
                            item_type = event.type.value
                            
                            if event.type == EventType.MESSAGE:
                                role = "assistant"
                            elif event.type in [
                                EventType.THOUGHT, EventType.TOOL_RESULT,
                                EventType.AGENT_START, EventType.ARTIFACT,
                                EventType.CRITIQUE_DOCUMENT, EventType.DRAFT_UPDATED
                            ]:
                                role = "agent"
                            else:
                                role = "system"
                            
                            chat_history_id = await append_to_chat_history(
                                session_id=current_session_id,
                                workflow_run_id=workflow_run_id,
                                item_type=item_type,
                                role=role,
                                content=event.content,
                                agent_name=event.agent,
                                tool_name=event.tool_name,
                                tool_args=event.tool_args,
                                tool_output=event.tool_output,
                                artifact_type=event.artifact_type,
                                artifact_title=event.artifact_title,
                                iteration=event.iteration,
                                version=event.version
                            )
                        
                        # Send to frontend
                        should_send_to_websocket = event.type not in [
                            EventType.MESSAGE,
                            EventType.THOUGHT
                        ]
                        
                        if should_send_to_websocket:
                            event_dict = event.to_dict()
                            if chat_history_id:
                                event_dict["id"] = chat_history_id
                            await websocket.send_json(event_dict)
                
                except asyncio.TimeoutError:
                    await update_workflow_run(workflow_run_id, status="timeout")
                except asyncio.CancelledError:
                    # Workflow was stopped by user
                    print("🛑 Workflow cancelled by user")
                except Exception as e:
                    print(f"Event streaming error: {e}")
                    await update_workflow_run(workflow_run_id, status="failed")
            
            # Send workflow running status
            await websocket.send_json({
                "type": "workflow_status",
                "running": True,
                "canResume": False
            })
            
            # Run both tasks concurrently, tracking the graph task
            consumer_task = asyncio.create_task(stream_events())
            running_task = asyncio.create_task(run_graph())
            
            try:
                await asyncio.gather(running_task, consumer_task)
            except asyncio.CancelledError:
                # Stop was requested
                pass
            finally:
                # Send final status (may be resumable if stopped mid-execution)
                try:
                    compiled_graph = get_compiled_graph()
                    state = await compiled_graph.aget_state(thread_config)
                    if state and state.next:
                        pending_nodes = list(state.next)
                        # Don't show Resume if at HITL node (approval modal handles it)
                        is_hitl = "await_plan_approval" in pending_nodes
                        can_resume = not is_hitl
                    else:
                        can_resume = False
                except Exception:
                    can_resume = False
                
                await websocket.send_json({
                    "type": "workflow_status",
                    "running": False,
                    "canResume": can_resume
                })
    
    except WebSocketDisconnect:
        print("Client disconnected")
        # Cancel both tasks if any (checkpoint already saved)
        if running_task and not running_task.done():
            running_task.cancel()
            try:
                await running_task
            except asyncio.CancelledError:
                pass
        if consumer_task and not consumer_task.done():
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
        
        # Close emitter to stop background threads from emitting stale events
        from backend.events import get_emitter, clear_emitter
        current_emitter = get_emitter()
        if current_emitter:
            current_emitter.close()
        clear_emitter()
        
        print("✅ Orphaned tasks cancelled - checkpoint preserved")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Also close emitter on error
        from backend.events import get_emitter, clear_emitter
        current_emitter = get_emitter()
        if current_emitter:
            current_emitter.close()
        clear_emitter()
        
        try:
            await websocket.close()
        except:
            pass
