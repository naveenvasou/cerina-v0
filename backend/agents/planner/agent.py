"""
Production-Grade Planner Agent - LangGraph Subgraph Implementation
"""

import json
from typing import Optional, List, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from backend.settings import settings
from backend.tools.clinical import ClinicalSearchTool, SafetyAdversaryTool
from backend.events import get_emitter

from backend.agents.planner.schemas import PlanOutput
from backend.agents.planner.state import PlannerState
from backend.agents.planner.prompts import (
    REASONING_SYSTEM_PROMPT, DRAFTING_SYSTEM_PROMPT, 
    REVISION_REASONING_PROMPT, REVISION_DRAFTING_PROMPT
)


class PlannerAgent:
    """
    Production-grade Planner Agent implemented as a LangGraph Subgraph.
    
    Follows the 3-Node "Researcher-Writer" pattern:
    1. Reasoning - Analyzes and decides on tool calls
    2. Tools - Executes tools via ToolNode
    3. Drafting - Synthesizes final structured output
    """
    
    def __init__(self, reasoning_model: str = "gemini-2.5-flash-lite", drafting_model: str = "gemini-2.5-flash-lite"):
        """
        Initialize the Planner Subgraph.
        
        Args:
            reasoning_model: Model for the reasoning node (default: gemini-flash-latest)
            drafting_model: Model for the drafting node (default: gemini-flash-latest)
        """
        # Initialize Tools
        self.tools = [ClinicalSearchTool(), SafetyAdversaryTool()]
        self.tools_by_name = {tool.name: tool for tool in self.tools}
        
        # Reasoning LLM (with tools bound)
        self.reasoning_llm = ChatGoogleGenerativeAI(
            model=reasoning_model,
            temperature=0.75,  # Temperature ~0.4 for balanced reasoning
            google_api_key=settings.GEMINI_API_KEY,
            thinking_budget=-1,
            include_thoughts=True,
        ).bind_tools(self.tools)
        
        # Drafting LLM (with structured output, no tools)
        self.drafting_llm = ChatGoogleGenerativeAI(
            model=drafting_model,
            temperature=0.5,  # Temperature 0.0 for deterministic output
            google_api_key=settings.GEMINI_API_KEY,
        ).with_structured_output(PlanOutput)
        
        # Build the subgraph
        self.graph = self._build_graph()
    
    def _emit(self, event_type: str, **kwargs):
        """Emit event if emitter is available."""
        emitter = get_emitter()
        if emitter:
            if event_type == "thought":
                emitter.emit_thought("planner", kwargs.get("content", ""))
            elif event_type == "thought_chunk":
                emitter.emit_thought_chunk("planner", kwargs.get("content", ""))
            elif event_type == "message_chunk":
                emitter.emit_message_chunk("planner", kwargs.get("content", ""))
            elif event_type == "message":
                emitter.emit_message("planner", kwargs.get("content", ""))
            elif event_type == "tool_call":
                emitter.emit_tool_call("planner", kwargs.get("tool_name", ""), kwargs.get("tool_args", {}))
            elif event_type == "tool_result":
                emitter.emit_tool_result("planner", kwargs.get("tool_name", ""), kwargs.get("tool_output", ""), kwargs.get("tool_args"))
            elif event_type == "artifact":
                emitter.emit_artifact("planner", kwargs.get("content", ""), kwargs.get("artifact_type", ""), kwargs.get("title", ""))
            elif event_type == "status":
                emitter.emit_status("planner", kwargs.get("content", ""))
            elif event_type == "agent_start":
                emitter.emit_agent_start("Planner Agent", kwargs.get("content", ""))
            elif event_type == "agent_memory":
                emitter.emit_agent_memory("Planner Agent", kwargs.get("messages", []), kwargs.get("scratchpad", ""))
    
    def _extract_text_content(self, content) -> str:
        """Extract text content from various response formats."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(part["text"])
                    if "thinking" in part:
                        text_parts.append(f"[Thinking] {part['thinking']}")
            return " ".join(text_parts)
        return str(content)
    
    def _serialize_messages(self, messages: list) -> list:
        """Convert LangChain messages to serializable dicts for Memory popup."""
        serialized = []
        for msg in messages:
            msg_dict = {
                "type": msg.__class__.__name__,
                "content": self._extract_text_content(msg.content)
            }
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            if hasattr(msg, 'name') and msg.name:
                msg_dict["name"] = msg.name
            if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            serialized.append(msg_dict)
        return serialized
    
    # -------------------------------------------------------------------------
    # NODE 1: REASONING (\"The Researcher\") - WITH STREAMING
    # -------------------------------------------------------------------------
    def _reasoning_node(self, state: PlannerState) -> dict:
        """
        Reasoning node - Analyzes the request and decides on tool calls.
        
        Uses streaming to emit thought chunks in real-time.
        In revision mode, uses REVISION_REASONING_PROMPT to produce change instructions.
        """
        messages = state["messages"]
        iteration = state.get("iteration_count", 0)
        is_revision = state.get("is_revision", False)
        
        # Choose system prompt based on mode
        if is_revision:
            system_prompt = REVISION_REASONING_PROMPT
        else:
            system_prompt = REASONING_SYSTEM_PROMPT
        
        system_msg = SystemMessage(content=system_prompt)
        messages_to_send = [system_msg] + list(messages)
        
        # Stream the reasoning LLM response
        accumulated_text = ""
        accumulated_thoughts = ""
        accumulated_tool_calls = []
        final_response = None
        
        try:
            for chunk in self.reasoning_llm.stream(messages_to_send):
                # Process chunk content
                if hasattr(chunk, 'content'):
                    if isinstance(chunk.content, str) and chunk.content:
                        # Direct string is treated as text output
                        self._emit("message_chunk", content=chunk.content)
                        accumulated_text += chunk.content
                        accumulated_thoughts += chunk.content  # Add text to scratchpad as requested
                        
                    elif isinstance(chunk.content, list):
                        for part in chunk.content:
                            if isinstance(part, str) and part:
                                # String in list is treated as text output
                                self._emit("message_chunk", content=part)
                                accumulated_text += part
                                accumulated_thoughts += part  # Add text to scratchpad as requested
                                
                            elif isinstance(part, dict):
                                if 'thinking' in part and part['thinking']:
                                    # Thinking blocks
                                    self._emit("thought_chunk", content=part['thinking'])
                                    accumulated_thoughts += f"[Thinking] {part['thinking']}"
                                    
                                if 'text' in part and part['text']:
                                    # Text blocks
                                    self._emit("message_chunk", content=part['text'])
                                    accumulated_text += part['text']
                                    accumulated_thoughts += part['text']  # Add text to scratchpad as requested
                
                # Accumulate tool calls (they come at the end or as chunks)
                if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    for tc in chunk.tool_calls:
                        # Clean up tool call to only include required fields
                        if isinstance(tc, dict) and 'name' in tc:
                            clean_tc = {
                                'name': tc['name'],
                                'args': tc.get('args', {}),
                                'id': tc.get('id', f"tool_{len(accumulated_tool_calls)}")
                            }
                            accumulated_tool_calls.append(clean_tc)
                
                # Skip tool_call_chunks - they contain 'index' which breaks AIMessage
                # Complete tool_calls come at the end of streaming
                
                # Keep the last chunk as reference
                final_response = chunk
               
                
        except Exception as e:
            print(f"Streaming error: {e}, falling back to invoke()")
            # Fallback to non-streaming
            response = self.reasoning_llm.invoke(messages_to_send)
            thoughts = self._extract_text_content(response.content)
            print("response: ",response)
            print("thoughts: ",thoughts)
            if thoughts:
                self._emit("thought", content=thoughts)
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    self._emit("tool_call", tool_name=tool_call["name"], tool_args=tool_call["args"])
            scratchpad = state.get("internal_scratchpad", "") or ""
            if thoughts:
                scratchpad += f"\n\n## Iteration {iteration + 1} - Reasoning\n{thoughts}"
            return {
                "messages": [response],
                "internal_scratchpad": scratchpad,
                "iteration_count": iteration + 1
            }
        
        # Check if we got any content - if not, fallback to invoke
        if not accumulated_text and not accumulated_tool_calls:
            print("Streaming returned empty, falling back to invoke()")
            response = self.reasoning_llm.invoke(messages_to_send)
            thoughts = self._extract_text_content(response.content)
            if thoughts:
                self._emit("thought", content=thoughts)
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    self._emit("tool_call", tool_name=tool_call["name"], tool_args=tool_call["args"])
            scratchpad = state.get("internal_scratchpad", "") or ""
            if thoughts:
                scratchpad += f"\n\n## Iteration {iteration + 1} - Reasoning\n{thoughts}"
            return {
                "messages": [response],
                "internal_scratchpad": scratchpad,
                "iteration_count": iteration + 1
            }
        
        # Build the final AIMessage from accumulated data
        from langchain_core.messages import AIMessage as AIMsg
        
        # If we didn't get tool_calls during streaming, check the final chunk
        if not accumulated_tool_calls and final_response:
            if hasattr(final_response, 'tool_calls') and final_response.tool_calls:
                for tc in final_response.tool_calls:
                    if isinstance(tc, dict) and 'name' in tc:
                        clean_tc = {
                            'name': tc['name'],
                            'args': tc.get('args', {}),
                            'id': tc.get('id', f"tool_{len(accumulated_tool_calls)}")
                        }
                        accumulated_tool_calls.append(clean_tc)
        
        response = AIMsg(
            content=accumulated_text,
            tool_calls=accumulated_tool_calls if accumulated_tool_calls else []
        )
        
        # ===================================================================
        # EMIT FINAL EVENTS FOR PERSISTENCE
        # Chunks are for real-time display, but we need final events for 
        # ChatHistory persistence so history loads correctly on refresh
        # ===================================================================
        
        # Emit final thought if we have any thinking content
        # (Note: accumulated_thoughts includes both thinking and text)
        if accumulated_thoughts:
            self._emit("thought", content=accumulated_thoughts)
        
        # Emit final message if we have accumulated text
        if accumulated_text and accumulated_text.strip():
            self._emit("message", content=accumulated_text)
        
        # Emit tool calls if present
        if accumulated_tool_calls:
            for tool_call in accumulated_tool_calls:
                self._emit("tool_call", 
                          tool_name=tool_call["name"], 
                          tool_args=tool_call["args"])
        
        # Update scratchpad with structured reasoning summary
        scratchpad = state.get("internal_scratchpad", "") or ""
        if accumulated_thoughts:
            scratchpad += f"\n\n## Iteration {iteration + 1} - Reasoning\n{accumulated_thoughts}"
        
        return {
            "messages": [response],
            "internal_scratchpad": scratchpad,
            "iteration_count": iteration + 1
        }
    
    # -------------------------------------------------------------------------
    # NODE 2: TOOLS ("The Executor")
    # -------------------------------------------------------------------------
    def _tools_node(self, state: PlannerState) -> dict:
        """
        Tools node - Executes tool calls using LangGraph's prebuilt ToolNode.
        
        Uses the prebuilt ToolNode for reliable execution.
        """
        # Get the last message (should be AIMessage with tool_calls)
        messages = state["messages"]
        last_message = messages[-1]
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}
        
        # Execute tools and collect results
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call.get("id", f"tool_{tool_name}")
            
            # Execute the tool
            tool = self.tools_by_name.get(tool_name)
            if tool:
                try:
                    result = tool.invoke(tool_args)
                except Exception as e:
                    result = f"Tool execution error: {str(e)}"
            else:
                result = f"Tool '{tool_name}' not found."
            
            # Emit tool result (with args so history has complete info)
            self._emit("tool_result", tool_name=tool_name, tool_output=str(result), tool_args=tool_args)
            
            # Create ToolMessage
            tool_messages.append(ToolMessage(
                tool_call_id=tool_id,
                content=str(result),
                name=tool_name
            ))
        
        return {"messages": tool_messages}
    
    # -------------------------------------------------------------------------
    # NODE 3: DRAFTING ("The Writer")
    # -------------------------------------------------------------------------
    def _drafting_node(self, state: PlannerState) -> dict:
        """
        Drafting node - Synthesizes all gathered information into the final plan.
        
        Uses structured output to guarantee the PlanOutput schema.
        In revision mode, uses a different prompt to preserve the reasoning node's revisions.
        """
        is_revision = state.get("is_revision", False)
        
        if is_revision:
            pass
            #self._emit("status", content="Extracting revised plan...")
        else:
            self._emit("status", content="Synthesizing final clinical plan...")
        
        messages = state["messages"]
        scratchpad = state.get("internal_scratchpad", "")
        previous_plan = state.get("previous_plan", "")
        
        # Choose prompt based on revision mode
        if is_revision:
            # REVISION MODE: Apply change instructions to the previous plan
            self._emit("status", content="Applying revisions to plan...")
            system_prompt = REVISION_DRAFTING_PROMPT
            
            # Parse previous plan to extract specific items
            try:
                import json
                prev_plan_dict = json.loads(previous_plan) if previous_plan else {}
                evidence_anchors = prev_plan_dict.get("evidence_anchors", [])
                evidence_count = len(evidence_anchors)
                # Create explicit list of existing anchors
                existing_anchors_str = "\n".join([
                    f"   - {a.get('source', 'Unknown')}: {a.get('note', '')[:50]}..."
                    for a in evidence_anchors
                ])
            except:
                evidence_count = 0
                existing_anchors_str = "(none)"
            
            # Get the last AIMessage which contains the change instructions
            change_instructions = ""
            for msg in reversed(messages):
                if type(msg).__name__ == "AIMessage" and not getattr(msg, 'tool_calls', None):
                    change_instructions = self._extract_text_content(msg.content)
                    break
            
            human_content = f"""YOU MUST APPLY THE CHANGES BELOW. DO NOT JUST COPY THE PREVIOUS PLAN.

## CHANGE INSTRUCTIONS (from reasoning node):
{change_instructions}

---

## CURRENT EVIDENCE ANCHORS IN PREVIOUS PLAN ({evidence_count} items):
{existing_anchors_str}

## IF THE INSTRUCTIONS SAY "ADD EVIDENCE ANCHOR":
Your output MUST have {evidence_count + 1} evidence anchors:
- All {evidence_count} existing ones listed above
- PLUS the new one from the change instructions

---

## PREVIOUS PLAN (base for your revisions):
```json
{previous_plan}
```

## YOUR TASK:
1. Read the CHANGE INSTRUCTIONS carefully
2. Apply EACH change to the previous plan
3. Your output must reflect the changes
4. If adding an evidence anchor, your output must have {evidence_count + 1} anchors"""
        else:
            # FRESH MODE: Synthesize from scratch
            system_prompt = DRAFTING_SYSTEM_PROMPT
            human_content = f"""Review the following conversation history and synthesize the final clinical plan.

            ## Reasoning Summary:
            {scratchpad}

            ## Full Conversation:
            {self._format_messages_for_drafting(messages)}

            Now produce the final structured clinical plan specification."""
        
        drafting_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content)
        ]
        
        # Call the drafting LLM with structured output
        try:
            plan_output: PlanOutput = self.drafting_llm.invoke(drafting_messages)
            
            # Emit the final artifact
            import json
            plan_dict = plan_output.model_dump()
            plan_str = json.dumps(plan_dict, indent=2)
            self._emit("artifact", 
                      content=plan_str, 
                      artifact_type="clinical_protocol", 
                      title="Clinical Protocol Specification")
            
            return {"final_plan_output": plan_output}
            
        except Exception as e:
            # Fallback: emit error and return None
            self._emit("thought", content=f"Error during plan synthesis: {str(e)}")
            return {"final_plan_output": None}
    
    def _format_messages_for_drafting(self, messages: list) -> str:
        """Format message history with emphasis on tool outputs for grounding."""
        formatted = []
        tool_outputs = []  # Collect separately for prominent display
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted.append(f"**User Request**: {msg.content}")
            elif isinstance(msg, AIMessage):
                content = self._extract_text_content(msg.content)
                if content:
                    formatted.append(f"**Assistant Reasoning**: {content}")
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        formatted.append(f"  → Tool Call: {tc['name']}({tc['args']})")
            elif isinstance(msg, ToolMessage):
                # Collect tool outputs for prominent display
                tool_outputs.append(f"### {msg.name}\n{msg.content}")
        
        # Structure output with tool results prominently displayed
        result = "\n\n".join(formatted)
        if tool_outputs:
            result += "\n\n" + "="*60 + "\n"
            result += "## CLINICAL EVIDENCE FROM TOOLS (USE FOR GROUNDING)\n"
            result += "="*60 + "\n\n"
            result += "\n\n---\n\n".join(tool_outputs)
        return result
    
    # -------------------------------------------------------------------------
    # ROUTING LOGIC
    # -------------------------------------------------------------------------
    def _should_continue(self, state: PlannerState) -> str:
        """
        Routing function from Reasoning node.
        
        Returns:
            "tools" - If tool_calls are present in the last message
            "drafting" - If no tool calls (ready for final synthesis)
        """
        messages = state["messages"]
        iteration = state.get("iteration_count", 0)
        
        # Safety limit: max 5 iterations
        if iteration >= 5:
            return "drafting"
        
        # Check the last message for tool calls
        if messages:
            last_message = messages[-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
        
        return "drafting"
    
    # -------------------------------------------------------------------------
    # GRAPH CONSTRUCTION
    # -------------------------------------------------------------------------
    def _build_graph(self) -> StateGraph:
        """Build and compile the LangGraph subgraph."""
        
        # Create the graph with PlannerState
        graph = StateGraph(PlannerState)
        
        # Add nodes
        graph.add_node("reasoning", self._reasoning_node)
        graph.add_node("tools", self._tools_node)
        graph.add_node("drafting", self._drafting_node)
        
        # Set entry point
        graph.set_entry_point("reasoning")
        
        # Add conditional edge from reasoning
        graph.add_conditional_edges(
            "reasoning",
            self._should_continue,
            {
                "tools": "tools",
                "drafting": "drafting"
            }
        )
        
        # Tools always go back to reasoning
        graph.add_edge("tools", "reasoning")
        
        # Drafting goes to END
        graph.add_edge("drafting", END)
        
        # Compile and return
        return graph.compile()
    
    # -------------------------------------------------------------------------
    # PUBLIC INTERFACE
    # -------------------------------------------------------------------------
    def invoke(self, state: dict) -> dict:
        """
        Execute the planner subgraph.
        
        Args:
            state: Input state with 'user_query' key
            
        Returns:
            dict with 'plan' (JSON string) and 'planner_trace' (empty, events streamed)
        """
        user_query = state.get('user_query', '')
        
        # HITL revision context
        hitl_feedback = state.get('hitl_feedback', '')
        revision_count = state.get('plan_revision_count', 0)
        previous_plan = state.get('plan', '')
        previous_scratchpad = state.get('planner_scratchpad', '')
        
        # Build the initial message content based on mode
        if revision_count > 0 and previous_plan:
            # REVISION MODE: Rich context with previous plan + feedback
            content = self._build_revision_prompt(
                user_query, previous_plan, hitl_feedback, 
                revision_count, previous_scratchpad
            )
            agent_start_msg = f"Revising clinical plan (revision #{revision_count})..."
        else:
            # FRESH MODE: Original query only
            content = user_query
            agent_start_msg = "Starting clinical planning analysis..."
        
        # Emit agent_start event
        self._emit("agent_start", content=agent_start_msg)
        
        # Emit start status
        self._emit("status", content="Planning..." if revision_count == 0 else f"Revising plan...")
        
        # Initialize the subgraph state
        # For revisions, seed the scratchpad with previous context
        initial_scratchpad = previous_scratchpad if revision_count > 0 else ""
        is_revision_mode = revision_count > 0 and bool(previous_plan)
        
        initial_state: PlannerState = {
            "messages": [HumanMessage(content=content)],
            "internal_scratchpad": initial_scratchpad,
            "final_plan_output": None,
            "iteration_count": 0,
            "is_revision": is_revision_mode,
            "previous_plan": previous_plan if is_revision_mode else None
        }
        
        # Run the subgraph (planner decides if tools are needed)
        final_state = self.graph.invoke(initial_state)
        
        # Extract the final plan
        plan_output = final_state.get("final_plan_output")
        
        if plan_output:
            plan_str = json.dumps(plan_output.model_dump(), indent=2)
        else:
            plan_str = "{}"
        
        # Emit agent memory for the Memory popup
        self._emit(
            "agent_memory", 
            messages=self._serialize_messages(final_state.get("messages", [])),
            scratchpad=final_state.get("internal_scratchpad", "")
        )
        
        return {
            "plan": plan_str,
            "planner_scratchpad": final_state.get("internal_scratchpad", ""),
            "planner_trace": []  # Trace is streamed via events
        }
    
    def _build_revision_prompt(self, query: str, plan: str, feedback: str, 
                               count: int, scratchpad: str) -> str:
        """
        Build a revision prompt that asks for CHANGE INSTRUCTIONS, not the final plan.
        
        The reasoning node should analyze the feedback and produce instructions for the drafting node.
        """
        return f"""[PLAN REVISION #{count}]

## Original User Request
{query}

## Current Plan (what needs to be revised)
```json
{plan}
```

## Previous Reasoning & Tool Outputs
{scratchpad if scratchpad else "(No previous reasoning available)"}

## User's Requested Changes
{feedback}

## YOUR TASK - PRODUCE CHANGE INSTRUCTIONS

Analyze the user's feedback and determine what changes are needed.

1. If the user's feedback requires NEW information (e.g., "add more evidence"):
   - Call the appropriate tool to gather that information
   - Include the new information in your change instructions

2. If the feedback is structural (e.g., "add more steps"):
   - No tools needed
   - Just describe what needs to change

## OUTPUT FORMAT
Provide clear CHANGE INSTRUCTIONS for the drafting node:

```
CHANGE INSTRUCTIONS:
1. [field_name]: [what to add/modify/remove]
2. [field_name]: [what to add/modify/remove]
...
```

⚠️ DO NOT output the final revised plan JSON - that's the drafting node's job.
Just describe the changes that need to be made.
"""
    
    async def astream(self, state: dict):
        """
        Async streaming execution of the planner subgraph.
        
        Yields events as they occur for real-time streaming.
        
        Args:
            state: Input state with 'user_query' key
            
        Yields:
            Tuples of (node_name, state_update)
        """
        user_query = state.get('user_query', '')
        
        # Initialize the subgraph state
        initial_state: PlannerState = {
            "messages": [HumanMessage(content=user_query)],
            "internal_scratchpad": "",
            "final_plan_output": None,
            "iteration_count": 0
        }
        
        # Stream the subgraph execution
        async for event in self.graph.astream(initial_state):
            yield event


if __name__ == "__main__":
    print("Testing Planner Subgraph...")
    
    planner = PlannerAgent()
    
    test_query = "I need a graded exposure exercise for a patient with social anxiety who is afraid of public speaking."
    
    result = planner.invoke({"user_query": test_query})
    
    print("\n" + "="*60)
    print("FINAL PLAN OUTPUT:")
    print("="*60)
    print(result["plan"])
