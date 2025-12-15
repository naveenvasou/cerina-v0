"""
Deterministic Drafting Agent - LangGraph Subgraph Implementation

A 6-agent pipeline that produces clinically accurate, low-hallucination CBT exercises:

1. ProtocolDecompositionAgent - Extracts hard constraints (protocol contract)
2. TherapeuticMechanismMapper - Models psychological learning mechanisms
3. ExerciseSkeletonAgent - Defines frozen structural blueprint
4. SectionDraftAgent (loop) - Drafts sections sequentially with full context
5. DraftAssembler - Pure function that assembles raw draft
6. PresentationSynthesizer - Formats and compresses without changing clinical content

Design Principles:
- Structure before language
- Mechanisms before prose
- One coherent writer, many constraints
- Sequential drafting, not parallel writing
- All prior outputs are read-only
- No agent invents new sections, goals, or rules
"""

import json
from typing import Optional, Dict, Any, Literal

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from backend.settings import settings
from backend.events import get_emitter

from backend.agents.draftsman.schemas import (
    ProtocolContract,
    MechanismMap,
    ExerciseSkeleton,
    SectionDraft,
    DraftV0
)
from backend.agents.draftsman.state import DraftsmanState
from backend.agents.draftsman.prompts import (
    PROTOCOL_DECOMPOSITION_PROMPT,
    MECHANISM_MAPPER_PROMPT,
    SKELETON_AGENT_PROMPT,
    SECTION_DRAFT_PROMPT,
    PRESENTATION_SYNTHESIZER_PROMPT
)


class DraftsmanAgent:
    """
    Deterministic Drafting Agent implemented as a LangGraph Subgraph.
    
    Uses a sequential 6-stage pipeline with a controlled loop for section drafting.
    NO tool use, NO parallel execution, NO free-form generation.
    """
    
    def __init__(
        self, 
        model: str = "gemini-2.5-flash",
        temperature: float = 0.6
    ):
        """
        Initialize the Deterministic Drafting Subgraph.
        
        Args:
            model: LLM model for all agents
            temperature: Temperature for generation (lower = more deterministic)
        """
        # All agents use the same base model with structured output
        self.base_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=settings.GEMINI_API_KEY,
            thinking_budget=-1,
            include_thoughts=True,
        )
        
        # Structured output LLMs for each agent
        self.protocol_decomposition_llm = self.base_llm #.with_structured_output(ProtocolContract)
        self.mechanism_mapper_llm = self.base_llm.with_structured_output(MechanismMap)
        self.skeleton_agent_llm = self.base_llm.with_structured_output(ExerciseSkeleton)
        self.section_draft_llm = self.base_llm.with_structured_output(SectionDraft)
        
        # Presentation Synthesizer uses raw text output (not structured)
        self.presentation_synthesizer_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.2,  # Lower temperature for faithful formatting
            google_api_key=settings.GEMINI_API_KEY,
        )
        
        # Build the subgraph
        self.graph = self._build_graph()
    
    # =========================================================================
    # EVENT EMISSION HELPERS
    # =========================================================================
    def _emit(self, event_type: str, **kwargs):
        """Emit event if emitter is available."""
        emitter = get_emitter()
        if emitter:
            # print(f"DEBUG: Emitting {event_type} - Emitter valid")
            if event_type == "thought":
                emitter.emit_thought("draftsman", kwargs.get("content", ""))
            elif event_type == "thought_chunk":
                emitter.emit_thought_chunk("draftsman", kwargs.get("content", ""))
            elif event_type == "message_chunk":
                emitter.emit_message_chunk("draftsman", kwargs.get("content", ""))
            elif event_type == "message_end":
                emitter.emit_message_end("draftsman")
            elif event_type == "message":
                emitter.emit_message("draftsman", kwargs.get("content", ""))
            elif event_type == "status":
                emitter.emit_status("draftsman", kwargs.get("content", ""))
            elif event_type == "artifact":
                emitter.emit_artifact(
                    "draftsman", 
                    kwargs.get("content", ""), 
                    kwargs.get("artifact_type", ""),
                    kwargs.get("title", "")
                )
            elif event_type == "agent_memory":
                emitter.emit_agent_memory(
                    "Draftsman Agent",
                    kwargs.get("messages", []),
                    kwargs.get("scratchpad", "")
                )
            elif event_type == "agent_start":
                emitter.emit_agent_start("Draftsman Agent", kwargs.get("content", ""))
        else:
            import threading
            print(f"CRITICAL: Draftsman emit failed - Emitter is None for event {event_type} (thread: {threading.get_ident()})")
    
    def _format_protocol_contract_md(self, contract: dict) -> str:
        """Format ProtocolContract as readable Markdown."""
        lines = ["I've analyzed the clinical plan and extracted the following protocol constraints:\n"]
        
        # Protocol Invariants
        if contract.get("protocol_invariants"):
            lines.append("**Protocol Invariants**")
            for item in contract["protocol_invariants"]:
                lines.append(f"- {item}")
            lines.append("")
        
        # Required Components
        if contract.get("required_components"):
            lines.append("**Required Components**")
            for item in contract["required_components"]:
                lines.append(f"- {item}")
            lines.append("")
        
        # Forbidden Moves
        if contract.get("forbidden_moves"):
            lines.append("**Forbidden Moves**")
            for item in contract["forbidden_moves"]:
                lines.append(f"- {item}")
            lines.append("")
        
        # Allowed Flexibility
        if contract.get("allowed_flexibility"):
            lines.append("**Allowed Flexibility**")
            for item in contract["allowed_flexibility"]:
                lines.append(f"- {item}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_mechanism_map_md(self, mechanism_map: dict) -> str:
        """Format MechanismMap as readable Markdown."""
        lines = ["I have broken down the therapeutic mechanisms to be targeted into the following:\n"]
        
        # Target Mechanisms
        if mechanism_map.get("target_mechanisms"):
            
            for i, mech in enumerate(mechanism_map["target_mechanisms"], 1):
                lines.append(f"\n**{i}. {mech.get('mechanism', 'Unknown')}**")
                if mech.get('maladaptive_belief'):
                    lines.append(f"- *Maladaptive Belief:* {mech['maladaptive_belief']}")
                if mech.get('maintaining_behaviors'):
                    behaviors = ", ".join(mech['maintaining_behaviors'])
                    lines.append(f"- *Maintaining Behaviors:* {behaviors}")
                if mech.get('learning_goal'):
                    lines.append(f"- *Learning Goal:* {mech['learning_goal']}")
            lines.append("")
        
        # Required Learning Signals
        if mechanism_map.get("required_learning_signals"):
            lines.append("### 💡 Required Learning Signals")
            for item in mechanism_map["required_learning_signals"]:
                lines.append(f"- {item}")
            lines.append("")
        
        # Behavioral Requirements
        if mechanism_map.get("behavioral_requirements"):
            lines.append("### 🏃 Behavioral Requirements")
            for item in mechanism_map["behavioral_requirements"]:
                lines.append(f"- {item}")
            lines.append("")
        
        return "\n".join(lines)
    
    # =========================================================================
    # NODE 1: PROTOCOL DECOMPOSITION AGENT
    # =========================================================================
    def _protocol_decomposition_node(self, state: DraftsmanState) -> dict:
        """
        Protocol Decomposition Agent - Extracts protocol contract from planner output.
        
        Translates the planner's descriptive plan into hard constraints that
        drafting must not violate.
        
        Uses streaming to emit thinking/text chunks in real-time.
        NO writing, only constraint extraction.
        """
        import threading
        print(f"DEBUG: Protocol Decomposition running in Thread: {threading.get_ident()}")
        
        planner_output = state["planner_output"]
        
        # Stream the LLM response
        accumulated_text = ""
        accumulated_thoughts = ""
        
        try:
            messages = [
                SystemMessage(content=PROTOCOL_DECOMPOSITION_PROMPT),
                HumanMessage(content=f"""## Planner Output (PlanOutput):
                    {json.dumps(planner_output, indent=2)}

                    Extract the Protocol Contract from this plan. Focus on:
                    1. Protocol invariants from drafting_spec
                    2. Forbidden moves from safety_envelope.forbidden_content
                    3. Required components from drafting_spec.task_constraints
                    4. Allowed flexibility areas""")
                                ]
            
            # Stream using the base LLM (not structured output) for real-time chunks
            
            for chunk in self.protocol_decomposition_llm.stream(messages):
                
                if hasattr(chunk, 'content'):
                    if isinstance(chunk.content, str) and chunk.content:
                        # Direct string is JSON output - accumulate silently
                        accumulated_text += chunk.content
                        
                    elif isinstance(chunk.content, list):
                        for part in chunk.content:
                            if isinstance(part, str) and part:
                                # String parts - accumulate silently
                                accumulated_text += part
                                
                            elif isinstance(part, dict):
                                if 'thinking' in part and part['thinking']:
                                    # Thinking blocks - stream to user
                                    self._emit("thought_chunk", content=part['thinking'])
                                    accumulated_thoughts += part['thinking']
                                    
                                if 'text' in part and part['text']:
                                    # Text blocks (JSON) - accumulate silently
                                    accumulated_text += part['text']
            
            # Parse the accumulated text as JSON to extract ProtocolContract
            try:
                # Try to extract JSON from the response
                import re
                json_match = re.search(r'\{[\s\S]*\}', accumulated_text)
                if json_match:
                    contract_data = json.loads(json_match.group())
                    protocol_contract = ProtocolContract(**contract_data)
                else:
                    # Fallback: try to parse the whole text
                    contract_data = json.loads(accumulated_text)
                    protocol_contract = ProtocolContract(**contract_data)
                    
                contract_dict = protocol_contract.model_dump()
                
            except (json.JSONDecodeError, Exception) as parse_error:
                # If parsing fails, use structured output as fallback
                
                protocol_contract: ProtocolContract = self.protocol_decomposition_llm.invoke(messages)
                contract_dict = protocol_contract.model_dump()
            
            # Format ProtocolContract as readable Markdown and emit
            formatted_md = self._format_protocol_contract_md(contract_dict)
            self._emit("message_chunk", content=formatted_md)
            self._emit("message_end")
            # Emit final thought for persistence (accumulated during streaming)
            if accumulated_thoughts:
                self._emit("thought", content=accumulated_thoughts)
            # Emit final message for persistence to ChatHistory
            self._emit("message", content=formatted_md)
            
            return {"protocol_contract": contract_dict}
            
        except Exception as e:
            # Fallback: extract directly from planner output
            return {
                "protocol_contract": {
                    "protocol_invariants": [],
                    "required_components": [],
                    "forbidden_moves": planner_output.get("safety_envelope", {}).get("forbidden_content", []),
                    "allowed_flexibility": []
                }
            }
    
    # =========================================================================
    # NODE 2: THERAPEUTIC MECHANISM MAPPER
    # =========================================================================
    def _mechanism_mapper_node(self, state: DraftsmanState) -> dict:
        """
        Therapeutic Mechanism Mapper - Models psychological learning mechanisms.
        
        Explicitly defines what psychological learning must occur for this
        exercise to be clinically effective.
        
        NO writing, only causal modeling.
        """
        #self._emit("status", content="[2/5] Mapping therapeutic mechanisms...")
        
        planner_output = state["planner_output"]
        protocol_contract = state["protocol_contract"]
        
        try:
            self._emit("thought", content="Modeling therapeutic mechanisms: beliefs → behaviors → learning goals...")
            
            # Call structured output LLM
            mechanism_map: MechanismMap = self.mechanism_mapper_llm.invoke([
                SystemMessage(content=MECHANISM_MAPPER_PROMPT),
                HumanMessage(content=f"""## Planner Output:
                {json.dumps(planner_output, indent=2)}

                ## Protocol Contract:
                {json.dumps(protocol_contract, indent=2)}

                Model the psychological mechanisms for this {planner_output.get('exercise_type', 'CBT exercise')}.
                Define what learning must occur for clinical effectiveness.""")
                            ])
            
            map_dict = mechanism_map.model_dump()
            
            # Format MechanismMap as readable Markdown and emit
            formatted_md = self._format_mechanism_map_md(map_dict)
            self._emit("message_chunk", content=formatted_md)
            self._emit("message_end")
            # Emit final message for persistence
            self._emit("message", content=formatted_md)
            
            return {"mechanism_map": map_dict}
            
        except Exception as e:
            #self._emit("thought", content=f"⚠️ Error in mechanism mapping: {str(e)}")
            # Fallback: basic mechanism structure
            return {
                "mechanism_map": {
                    "target_mechanisms": [{
                        "mechanism": "Behavioral activation",
                        "maladaptive_belief": "Unknown",
                        "maintaining_behaviors": [],
                        "learning_goal": "Symptom reduction through engagement"
                    }],
                    "required_learning_signals": ["Completion of exercise"],
                    "behavioral_requirements": ["Active participation"]
                }
            }
    
    # =========================================================================
    # NODE 3: EXERCISE SKELETON AGENT
    # =========================================================================
    def _skeleton_agent_node(self, state: DraftsmanState) -> dict:
        """
        Exercise Skeleton Agent - Defines frozen structural blueprint.
        
        Creates the section structure that will guide sequential drafting.
        This structure is FINAL and cannot be modified during drafting.
        
        NO content, only structure.
        """
        #self._emit("status", content="[3/5] Defining exercise structure...")
        
        planner_output = state["planner_output"]
        protocol_contract = state["protocol_contract"]
        mechanism_map = state["mechanism_map"]
        
        try:
            self._emit("thought", content="Creating frozen structural blueprint with section purposes and requirements...")
            
            # Call structured output LLM
            skeleton: ExerciseSkeleton = self.skeleton_agent_llm.invoke([
                SystemMessage(content=SKELETON_AGENT_PROMPT),
                HumanMessage(content=f"""## Planner Output:
                {json.dumps(planner_output, indent=2)}

                ## Protocol Contract:
                {json.dumps(protocol_contract, indent=2)}

                ## Mechanism Map:
                {json.dumps(mechanism_map, indent=2)}

                Define the structural skeleton for this {planner_output.get('exercise_type', 'CBT exercise')}.
                Each section must have a clear clinical purpose.""")
                            ])
            
            skeleton_dict = skeleton.model_dump()
            
            section_ids = [s["section_id"] for s in skeleton_dict["sections"]]
            skeleton_msg = f"✓ Skeleton: {len(skeleton_dict['sections'])} sections → {', '.join(section_ids)}"
            self._emit("message_chunk", content=skeleton_msg)
            self._emit("message_end")
            # Emit final message for persistence
            self._emit("message", content=skeleton_msg)
            
            return {
                "exercise_skeleton": skeleton_dict,
                "current_section_index": 0,
                "drafted_sections": {}
            }
            
        except Exception as e:
            #self._emit("thought", content=f"⚠️ Error in skeleton creation: {str(e)}")
            # Fallback: minimal skeleton
            return {
                "exercise_skeleton": {
                    "sections": [
                        {
                            "section_id": "introduction",
                            "purpose": "Orient the user to the exercise",
                            "required_elements": ["Exercise overview"],
                            "constraints": {"tone": "Supportive"}
                        },
                        {
                            "section_id": "main_content",
                            "purpose": "Deliver the core exercise",
                            "required_elements": ["Exercise steps"],
                            "constraints": {"format": "Numbered list"}
                        },
                        {
                            "section_id": "reflection",
                            "purpose": "Guide post-exercise reflection",
                            "required_elements": ["Reflection prompts"],
                            "constraints": {"tone": "Encouraging"}
                        }
                    ]
                },
                "current_section_index": 0,
                "drafted_sections": {}
            }
    
    # =========================================================================
    # NODE 4: SECTION DRAFT AGENT (called in loop)
    # =========================================================================
    def _section_draft_node(self, state: DraftsmanState) -> dict:
        """
        Section Draft Agent - Drafts one section at a time.
        
        Called repeatedly in a loop for each section in the skeleton.
        Has full awareness of all prior sections (read-only).
        
        WRITES content following strict constraints.
        """
        skeleton = state["exercise_skeleton"]
        sections = skeleton.get("sections", [])
        current_idx = state["current_section_index"]
        drafted_sections = state.get("drafted_sections", {})
        
        # Safety check
        if current_idx >= len(sections):
            return {}
        
        current_section = sections[current_idx]
        section_id = current_section["section_id"]
        
        #self._emit("status", content=f"[4/5] Drafting section: {section_id} ({current_idx + 1}/{len(sections)})")
        
        protocol_contract = state["protocol_contract"]
        mechanism_map = state["mechanism_map"]
        
        try:
            section_msg = f"Writing section '{section_id}' with purpose: {current_section['purpose']}..."
            self._emit("message_chunk", content=section_msg)
            self._emit("message_end")
            # Emit final message for persistence
            self._emit("message", content=section_msg)
            # Build prior sections context
            prior_sections_str = ""
            if drafted_sections:
                prior_sections_str = "\n\n".join([
                    f"### {sid}\n{content}" 
                    for sid, content in drafted_sections.items()
                ])
            else:
                prior_sections_str = "(No prior sections yet)"
            
            # Call structured output LLM
            section_draft: SectionDraft = self.section_draft_llm.invoke([
                SystemMessage(content=SECTION_DRAFT_PROMPT),
                HumanMessage(content=f"""## Section Spec (THIS IS YOUR TASK):
                    {json.dumps(current_section, indent=2)}

                    ## Protocol Contract (MUST OBEY):
                    {json.dumps(protocol_contract, indent=2)}

                    ## Mechanism Map (CLINICAL GOALS):
                    {json.dumps(mechanism_map, indent=2)}

                    ## Prior Sections (READ-ONLY):
                    {prior_sections_str}

                    ## Section Constraints:
                    - prior_sections_read_only: true
                    - no_new_sections: true  
                    - no_new_goals: true

                    Now draft the content for section '{section_id}' following its purpose and required_elements exactly.""")
                                ])
            
            draft_dict = section_draft.model_dump()
            
            # Update drafted sections
            new_drafted_sections = dict(drafted_sections)
            new_drafted_sections[draft_dict["section_id"]] = draft_dict["section_content"]
            
            #self._emit("thought_chunk", content=f"✓ Section '{section_id}' drafted ({len(draft_dict['section_content'])} chars)")
            
            return {
                "current_section_index": current_idx + 1,
                "drafted_sections": new_drafted_sections,
                "iteration_count": state.get("iteration_count", 0) + 1
            }
            
        except Exception as e:
            #self._emit("thought", content=f"⚠️ Error drafting section '{section_id}': {str(e)}")
            # Fallback: placeholder content
            new_drafted_sections = dict(drafted_sections)
            new_drafted_sections[section_id] = f"[Content for {section_id} could not be generated]"
            
            return {
                "current_section_index": current_idx + 1,
                "drafted_sections": new_drafted_sections,
                "iteration_count": state.get("iteration_count", 0) + 1
            }
    
    # =========================================================================
    # NODE 5: DRAFT ASSEMBLER (Non-LLM, Pure Function)
    # =========================================================================
    def _draft_assembler_node(self, state: DraftsmanState) -> dict:
        """
        Draft Assembler - Assembles final draft artifact.
        
        This is a PURE FUNCTION with no LLM calls.
        Simply orders sections and packages metadata.
        
        No rewriting, no interpretation, just assembly.
        """
        #self._emit("status", content="[5/6] Assembling raw draft...")
        
        skeleton = state["exercise_skeleton"]
        drafted_sections = state.get("drafted_sections", {})
        protocol_contract = state["protocol_contract"]
        mechanism_map = state["mechanism_map"]
        planner_output = state["planner_output"]
        
        # Order sections according to skeleton
        ordered_sections = {}
        for section_spec in skeleton.get("sections", []):
            section_id = section_spec["section_id"]
            if section_id in drafted_sections:
                ordered_sections[section_id] = drafted_sections[section_id]
        
        # Assemble DraftV0
        draft_v0 = {
            "exercise": ordered_sections,
            "metadata": {
                "exercise_type": planner_output.get("exercise_type", "CBT Exercise"),
                "protocol_contract": protocol_contract,
                "mechanism_map": mechanism_map,
                "skeleton": skeleton
            }
        }
        
        # Assemble Markdown for display
        markdown_parts = []
        exercise_type = planner_output.get("exercise_type", "CBT Exercise")
        markdown_parts.append(f"# {exercise_type}\n")
        
        for section_id, content in ordered_sections.items():
            # Convert section_id to title case for display
            section_title = section_id.replace("_", " ").title()
            markdown_parts.append(f"## {section_title}\n\n{content}\n")
        
        assembled_markdown = "\n".join(markdown_parts)
        
        #self._emit("thought", content=f"✓ Raw draft assembled: {len(ordered_sections)} sections, {len(assembled_markdown)} total characters")
        
        return {
            "draft_v0": draft_v0,
            "assembled_markdown": assembled_markdown
        }
    
    # =========================================================================
    # ROUTING LOGIC
    # =========================================================================
    def _should_continue_drafting(self, state: DraftsmanState) -> Literal["continue", "assemble"]:
        """
        Routing function for the section drafting loop.
        
        Returns:
            "continue" - More sections to draft
            "assemble" - All sections drafted, proceed to assembly
        """
        skeleton = state.get("exercise_skeleton", {})
        sections = skeleton.get("sections", [])
        current_idx = state.get("current_section_index", 0)
        iteration_count = state.get("iteration_count", 0)
        
        # Safety limit
        if iteration_count >= 20:
            #self._emit("thought", content="⚠️ Safety limit reached (20 iterations), proceeding to assembly")
            return "assemble"
        
        # Check if more sections to draft
        if current_idx < len(sections):
            return "continue"
        
        return "assemble"
    
    # =========================================================================
    # NODE 6: PRESENTATION SYNTHESIZER (LLM-based formatting)
    # =========================================================================
    def _presentation_synthesizer_node(self, state: DraftsmanState) -> dict:
        """
        Presentation Synthesizer - Final formatting pass.
        
        Reorganizes and compresses content WITHOUT changing clinical meaning.
        This fixes verbosity and poor formatting from section-by-section drafting.
        
        FORMATS content, does not REASON clinically.
        """
        #self._emit("status", content="[6/6] Synthesizing final presentation...")
        
        assembled_markdown = state.get("assembled_markdown", "")
        exercise_skeleton = state.get("exercise_skeleton", {})
        protocol_contract = state.get("protocol_contract", {})
        planner_output = state.get("planner_output", {})
        exercise_type = planner_output.get("exercise_type", "CBT Exercise")
        
        try:
            #self._emit("thought", content="Applying presentation formatting: merging repetition, adding tables, improving scannability...")
            
            # Stream the final synthesis for real-time visibility
            accumulated_content = ""
            
            for chunk in self.presentation_synthesizer_llm.stream([
                SystemMessage(content=PRESENTATION_SYNTHESIZER_PROMPT),
                HumanMessage(content=f"""## Exercise Type
                {exercise_type}

                ## Protocol Contract (DO NOT VIOLATE)
                {json.dumps(protocol_contract, indent=2)}

                ## Structure Reference
                {json.dumps(exercise_skeleton, indent=2)}

                ## Raw Draft (REFORMAT THIS)
                {assembled_markdown}

                Reformat the above draft for better presentation. Remember:
                - Merge repeated instructions into single blocks
                - Convert step-by-step repetition into tables where appropriate
                - Do NOT add new therapeutic content
                - Do NOT remove any clinical elements
                - Output clean, well-formatted Markdown ready for patient use.""")
                            ]):
                if hasattr(chunk, 'content') and chunk.content:
                    content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    #self._emit("message_chunk", content=content)
                    accumulated_content += content
            
            # Signal end of this streaming message
            self._emit("message_end")
            
            final_draft = accumulated_content if accumulated_content else assembled_markdown
            
            # Emit the final artifact
            self._emit(
                "artifact",
                content=final_draft,
                artifact_type="cbt_exercise",
                title=f"CBT Exercise: {exercise_type}"
            )
            
            #self._emit("thought", content=f"✓ Presentation synthesized: {len(final_draft)} chars (was {len(assembled_markdown)} chars)")
            
            return {"final_draft": final_draft}
            
        except Exception as e:
            self._emit("thought", content=f"⚠️ Error in presentation synthesis: {str(e)}. Using raw draft.")
            # Fallback: use assembled markdown as-is
            self._emit(
                "artifact",
                content=assembled_markdown,
                artifact_type="cbt_exercise",
                title=f"CBT Exercise: {exercise_type}"
            )
            return {"final_draft": assembled_markdown}
    
    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================
    def _build_graph(self) -> StateGraph:
        """Build and compile the deterministic LangGraph subgraph.
        
        NOTE: Presentation Synthesizer has been moved to the main graph.
        This subgraph now ends at draft_assembler.
        """
        
        graph = StateGraph(DraftsmanState)
        
        # Add nodes (5-stage pipeline - synthesizer moved to main graph)
        graph.add_node("protocol_decomposition", self._protocol_decomposition_node)
        graph.add_node("mechanism_mapper", self._mechanism_mapper_node)
        graph.add_node("skeleton_agent", self._skeleton_agent_node)
        graph.add_node("section_draft", self._section_draft_node)
        graph.add_node("draft_assembler", self._draft_assembler_node)
        
        # Set entry point
        graph.set_entry_point("protocol_decomposition")
        
        # Linear progression through analysis stages
        graph.add_edge("protocol_decomposition", "mechanism_mapper")
        graph.add_edge("mechanism_mapper", "skeleton_agent")
        graph.add_edge("skeleton_agent", "section_draft")
        
        # Conditional loop for section drafting
        graph.add_conditional_edges(
            "section_draft",
            self._should_continue_drafting,
            {
                "continue": "section_draft",
                "assemble": "draft_assembler"
            }
        )
        
        # Draft assembler → END (synthesizer is now in main graph)
        graph.add_edge("draft_assembler", END)
        
        return graph.compile()
    
    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================
    def invoke(self, state: dict) -> dict:
        """
        Execute the deterministic drafting subgraph.
        
        Args:
            state: Input state with 'plan' key (JSON string of PlanOutput)
            
        Returns:
            dict with:
            - 'draft' (Markdown string) - The assembled draft
            - 'current_draft' (Markdown string) - Same as draft, for reflection loop
            - 'protocol_contract' (dict) - Protocol constraints for critic reference
            - 'draft_versions' (list) - Initial version history
        """
        from datetime import datetime
        print("EMITTING AGENT START EVENT FOR DRAFTSMAN")
        # Emit agent_start event
        self._emit("agent_start", content="Starting deterministic CBT exercise drafting...")
        print("EMITTED AGENT START EVENT FOR DRAFTSMAN")
        plan_str = state.get('plan', '{}')
        
        # Parse plan JSON
        try:
            planner_output = json.loads(plan_str) if isinstance(plan_str, str) else plan_str
        except json.JSONDecodeError:
            planner_output = {}
        
        # Initialize the subgraph state
        initial_state: DraftsmanState = {
            "planner_output": planner_output,
            "protocol_contract": None,
            "mechanism_map": None,
            "exercise_skeleton": None,
            "current_section_index": 0,
            "drafted_sections": {},
            "draft_v0": None,
            "assembled_markdown": None,
            "final_draft": None,
            "iteration_count": 0
        }
        
        # Run the subgraph
        final_state = self.graph.invoke(initial_state)
        
        # Extract the assembled draft (synthesizer is now in main graph)
        draft_markdown = final_state.get("assembled_markdown", "")
        
        # Build protocol contract for critic
        protocol_contract = {
            "protocol_contract": final_state.get("protocol_contract"),
            "mechanism_map": final_state.get("mechanism_map"),
            "exercise_skeleton": final_state.get("exercise_skeleton")
        }
        
        # Initialize version history with first draft
        initial_version = {
            "version": 1,
            "content": draft_markdown,
            "timestamp": datetime.now().isoformat(),
            "status": "draft",
            "iteration": 0,
            "changes": "Initial draft from Draftsman Agent"
        }
        
        # Build scratchpad for memory popup
        scratchpad_parts = []
        if final_state.get("protocol_contract"):
            scratchpad_parts.append(f"## Protocol Contract\n{json.dumps(final_state['protocol_contract'], indent=2)}")
        if final_state.get("mechanism_map"):
            scratchpad_parts.append(f"## Mechanism Map\n{json.dumps(final_state['mechanism_map'], indent=2)}")
        if final_state.get("exercise_skeleton"):
            scratchpad_parts.append(f"## Exercise Skeleton\n{json.dumps(final_state['exercise_skeleton'], indent=2)}")
        
        # Emit agent memory
        self._emit(
            "agent_memory",
            messages=[],  # No conversation history in deterministic pipeline
            scratchpad="\n\n".join(scratchpad_parts)
        )
        
        # Emit the draft as artifact for canvas display
        exercise_type = planner_output.get("exercise_type", "CBT Exercise")
        self._emit(
            "artifact",
            content=draft_markdown,
            artifact_type="draft",
            title=f"Draft: {exercise_type}"
        )
        
        return {
            "draft": draft_markdown,
            "current_draft": draft_markdown,  # For reflection loop
            "protocol_contract": protocol_contract,
            "draft_versions": [initial_version],
            "reflection_iteration": 1  # Initialize reflection counter
        }


# =============================================================================
# STANDALONE TEST
# =============================================================================
if __name__ == "__main__":
    print("Testing Deterministic Drafting Subgraph...")
    
    # Example plan output (simulating PlannerAgent output)
    test_plan = json.dumps({
        "exercise_type": "Graded Exposure Hierarchy for Social Anxiety",
        "drafting_spec": {
            "task_constraints": {
                "step_count": "8-10 progressive steps",
                "progression_logic": "SUDS-based from 20 to 80",
                "focus_areas": "public speaking, meetings, introductions"
            },
            "style_rules": [
                "Steps must be specific and measurable",
                "Include SUDS anchor points",
                "Use second-person voice"
            ]
        },
        "safety_envelope": {
            "forbidden_content": [
                "Flooding without consent",
                "Imaginal exposure for trauma",
                "Medication recommendations"
            ],
            "special_conditions": [
                "Include disclaimer about pacing",
                "Remind user to work with therapist"
            ]
        },
        "critic_rubrics": {
            "safety": ["No flooding", "No trauma exposure"],
            "clinical_accuracy": ["Proper SUDS progression", "Evidence-based steps"],
            "usability": ["Clear instructions", "Measurable outcomes"]
        },
        "evidence_anchors": [
            {"source": "Craske et al., 2014", "note": "Inhibitory learning model"},
            {"source": "Hofmann, 2007", "note": "CBT for social anxiety"}
        ],
        "user_preview": "I'll create a graded exposure hierarchy to help you gradually build confidence in social situations."
    })
    
    draftsman = DraftsmanAgent()
    result = draftsman.invoke({"plan": test_plan})
    
    print("\n" + "="*60)
    print("FINAL DRAFT:")
    print("="*60)
    print(result["draft"])
