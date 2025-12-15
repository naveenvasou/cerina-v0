"""
WebSocket Routes

Handles WebSocket connections for real-time chat communication.
Delegates to:
- persistence.py for database operations
- node_handlers.py for graph node event processing
"""

from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from backend.graph import graph
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
                    try:
                        async for event in graph.astream(
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
                            state = await graph.aget_state(thread_config)
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
                                # When decision is "approved", this event is spuriously emitted
                                # because the node function re-runs on resume. Skip it and continue.
                                if decision == "approved":
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
            
            # Create workflow run
            workflow_run_id = await create_workflow_run(current_session_id, user_query)
            if not workflow_run_id:
                workflow_run_id = generate_workflow_run_id()
            
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
                try:
                    async for event in graph.astream(inputs, config=thread_config):
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
                except Exception as e:
                    print(f"Event streaming error: {e}")
                    await update_workflow_run(workflow_run_id, status="failed")
            
            # Run both tasks concurrently
            await asyncio.gather(run_graph(), stream_events())
    
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.close()
        except:
            pass
