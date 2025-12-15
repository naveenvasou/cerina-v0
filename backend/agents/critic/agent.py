"""
Critic Agent - Multi-perspective critique with 3 specialized critics.

Architecture:
1. Safety Critic - Evaluates patient safety
2. Clinical Accuracy Critic - Validates evidence-based practice
3. Tone/Empathy Critic - Ensures therapeutic alliance language
4. Consolidator - Synthesizes all critiques into unified document
"""

import json
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.settings import settings
from backend.events import get_emitter

from backend.agents.critic.schemas import (
    SafetyCritique,
    ClinicalAccuracyCritique,
    ToneEmpathyCritique,
    ConsolidatedCritique
)
from backend.agents.critic.state import CriticState
from backend.agents.critic.prompts import (
    SAFETY_CRITIC_PROMPT,
    CLINICAL_ACCURACY_CRITIC_PROMPT,
    TONE_EMPATHY_CRITIC_PROMPT,
    CONSOLIDATOR_PROMPT
)


class CriticAgent:
    """
    Multi-perspective Critique Agent implemented as a LangGraph Subgraph.
    
    Runs 3 specialized critics in sequence, then consolidates their outputs
    into a unified critique document for the revision agent.
    """
    
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.6
    ):
        """
        Initialize the Critic Agent.
        
        Args:
            model: LLM model for all critics
            temperature: Lower temperature for consistent evaluation
        """
        # Base LLM for all critics
        self.base_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=settings.GEMINI_API_KEY,
            thinking_budget=-1,
            include_thoughts=True,
        )
        
        # Structured output LLMs for each critic
        self.safety_llm = self.base_llm.with_structured_output(SafetyCritique)
        self.clinical_llm = self.base_llm.with_structured_output(ClinicalAccuracyCritique)
        self.tone_llm = self.base_llm.with_structured_output(ToneEmpathyCritique)
        self.consolidator_llm = self.base_llm.with_structured_output(ConsolidatedCritique)
        
        # Build the subgraph
        self.graph = self._build_graph()
    
    # =========================================================================
    # EVENT EMISSION HELPERS
    # =========================================================================
    def _emit(self, event_type: str, **kwargs):
        """Emit event if emitter is available."""
        emitter = get_emitter()
        if emitter:
            if event_type == "thought":
                emitter.emit_thought("critic", kwargs.get("content", ""))
            elif event_type == "thought_chunk":
                emitter.emit_thought_chunk("critic", kwargs.get("content", ""))
            elif event_type == "message_chunk":
                emitter.emit_message_chunk("critic", kwargs.get("content", ""))
            elif event_type == "message_end":
                emitter.emit_message_end("critic")
            elif event_type == "message":
                emitter.emit_message("critic", kwargs.get("content", ""))
            elif event_type == "status":
                emitter.emit_status("critic", kwargs.get("content", ""))
            elif event_type == "artifact":
                emitter.emit_artifact(
                    "critic",
                    kwargs.get("content", ""),
                    kwargs.get("artifact_type", ""),
                    kwargs.get("title", "")
                )
            elif event_type == "agent_memory":
                emitter.emit_agent_memory(
                    "Critic Agent",
                    kwargs.get("messages", []),
                    kwargs.get("scratchpad", "")
                )
            elif event_type == "agent_start":
                emitter.emit_agent_start("Critic Agent", kwargs.get("content", ""))
    
    # =========================================================================
    # NODE 1: SAFETY CRITIC
    # =========================================================================
    def _safety_critic_node(self, state: CriticState) -> dict:
        """
        Safety Critic - Evaluates draft for patient safety issues.
        """
        self._emit("status", content="🛡️ Safety Critic evaluating...")
        
        current_draft = state["current_draft"]
        plan = state.get("plan", {})
        
        # Get existing messages and scratchpad (for parallel execution merger)
        existing_messages = state.get("internal_messages") or []
        existing_scratchpad = state.get("internal_scratchpad") or ""
        
        # Extract safety-relevant info from plan
        safety_envelope = plan.get("safety_envelope", {})
        forbidden_content = safety_envelope.get("forbidden_content", [])
        special_conditions = safety_envelope.get("special_conditions", [])
        
        # Format the prompt
        formatted_prompt = SAFETY_CRITIC_PROMPT.format(
            forbidden_content=json.dumps(forbidden_content, indent=2) if forbidden_content else "None specified",
            special_conditions=json.dumps(special_conditions, indent=2) if special_conditions else "None specified"
        )
        
        user_prompt = f"""## Draft to Evaluate:

{current_draft[:1500]}...

Evaluate this draft for safety issues. Be thorough and conservative."""
        
        # Track the message for Memory popup
        new_messages = [
            {"type": "SystemMessage", "content": "Safety Critic Prompt (truncated for display)"},
            {"type": "HumanMessage", "content": user_prompt[:500] + "..."}
        ]
        
        # Track scratchpad entry
        scratchpad_entry = f"\n\n## 🛡️ Safety Critic Analysis\n"
        scratchpad_entry += f"- Forbidden content checked: {len(forbidden_content)} items\n"
        scratchpad_entry += f"- Special conditions: {len(special_conditions)} items\n"
        
        try:
            safety_critique: SafetyCritique = self.safety_llm.invoke([
                SystemMessage(content=formatted_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            critique_dict = safety_critique.model_dump()
            
            # Build AI response for messages
            new_messages.append({
                "type": "AIMessage",
                "content": f"Safety Review: {'Approved' if critique_dict['approved'] else 'Issues Found'}\n\nSummary: {critique_dict['summary']}"
            })
            
            # Add to scratchpad
            scratchpad_entry += f"- Result: {'✅ Approved' if critique_dict['approved'] else '❌ Issues Found'}\n"
            scratchpad_entry += f"- Issues: {len(critique_dict.get('issues', []))}\n"
            scratchpad_entry += f"- Summary: {critique_dict['summary']}\n"
            
            # Emit result
            status = "✅ Passed" if critique_dict["approved"] else f"❌ {len(critique_dict['issues'])} issues found"
            msg_content = f"**Safety Review:** {status}\n{critique_dict['summary']}"
            self._emit("message_chunk", content=msg_content)
            self._emit("message_end")
            self._emit("message", content=msg_content)  # For persistence
            
            return {
                "safety_critique": critique_dict,
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }
            
        except Exception as e:
            # Fallback: fail-safe (don't approve if we can't evaluate)
            self._emit("thought", content=f"⚠️ Safety evaluation error: {str(e)}")
            scratchpad_entry += f"- ERROR: {str(e)}\n"
            
            return {
                "safety_critique": {
                    "approved": False,
                    "issues": [{
                        "issue": "Safety evaluation failed - requires manual review",
                        "severity": "critical",
                        "location": None,
                        "recommendation": "Manually verify draft safety before proceeding"
                    }],
                    "summary": "Automatic safety evaluation failed. Manual review required."
                },
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }

    
    # =========================================================================
    # NODE 2: CLINICAL ACCURACY CRITIC
    # =========================================================================
    def _clinical_critic_node(self, state: CriticState) -> dict:
        """
        Clinical Accuracy Critic - Validates evidence-based therapeutic practice.
        """
        self._emit("status", content="🩺 Clinical Accuracy Critic evaluating...")
        
        current_draft = state["current_draft"]
        plan = state.get("plan", {})
        protocol_contract = state.get("protocol_contract", {})
        
        # Get existing messages and scratchpad (for parallel execution merger)
        existing_messages = state.get("internal_messages") or []
        existing_scratchpad = state.get("internal_scratchpad") or ""
        
        # Extract clinical accuracy info
        exercise_type = plan.get("exercise_type", "CBT Exercise")
        drafting_spec = plan.get("drafting_spec", {})
        required_components = drafting_spec.get("required_fields", [])
        critic_rubrics = plan.get("critic_rubrics", {})
        clinical_rubrics = critic_rubrics.get("clinical_accuracy", [])
        
        # Get mechanism goals from protocol contract if available
        mechanism_goals = protocol_contract.get("mechanism_map", {}).get("target_mechanisms", []) if protocol_contract else []
        mechanism_goals_str = json.dumps(mechanism_goals, indent=2) if mechanism_goals else "Not specified"
        
        formatted_prompt = CLINICAL_ACCURACY_CRITIC_PROMPT.format(
            exercise_type=exercise_type,
            required_components=json.dumps(required_components, indent=2) if required_components else "None specified",
            mechanism_goals=mechanism_goals_str,
            clinical_rubrics=json.dumps(clinical_rubrics, indent=2) if clinical_rubrics else "None specified"
        )
        
        user_prompt = f"""## Draft to Evaluate:

{current_draft[:1500]}...

Evaluate this draft for clinical accuracy and evidence-based practice."""
        
        # Track the message for Memory popup
        new_messages = [
            {"type": "SystemMessage", "content": "Clinical Accuracy Critic Prompt"},
            {"type": "HumanMessage", "content": f"Exercise: {exercise_type}, Components: {len(required_components)}"}
        ]
        
        # Track scratchpad entry
        scratchpad_entry = f"\n\n## 🩺 Clinical Accuracy Critic Analysis\n"
        scratchpad_entry += f"- Exercise type: {exercise_type}\n"
        scratchpad_entry += f"- Required components: {len(required_components)} items\n"
        scratchpad_entry += f"- Mechanism goals: {len(mechanism_goals)} targets\n"
        
        try:
            clinical_critique: ClinicalAccuracyCritique = self.clinical_llm.invoke([
                SystemMessage(content=formatted_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            critique_dict = clinical_critique.model_dump()
            
            # Build AI response for messages
            new_messages.append({
                "type": "AIMessage",
                "content": f"Clinical Review: {'Approved' if critique_dict['approved'] else 'Issues Found'}\n\nSummary: {critique_dict['summary']}"
            })
            
            # Add to scratchpad
            scratchpad_entry += f"- Result: {'✅ Approved' if critique_dict['approved'] else '❌ Issues Found'}\n"
            scratchpad_entry += f"- Issues: {len(critique_dict.get('issues', []))}\n"
            scratchpad_entry += f"- Evidence gaps: {len(critique_dict.get('evidence_gaps', []))}\n"
            scratchpad_entry += f"- Summary: {critique_dict['summary']}\n"
            
            # Emit result
            status = "✅ Passed" if critique_dict["approved"] else f"❌ {len(critique_dict['issues'])} issues found"
            msg_content = f"**Clinical Accuracy Review:** {status}\n{critique_dict['summary']}"
            self._emit("message_chunk", content=msg_content)
            self._emit("message_end")
            self._emit("message", content=msg_content)  # For persistence
            
            return {
                "clinical_critique": critique_dict,
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }
            
        except Exception as e:
            self._emit("thought", content=f"⚠️ Clinical evaluation error: {str(e)}")
            scratchpad_entry += f"- ERROR: {str(e)}\n"
            
            return {
                "clinical_critique": {
                    "approved": False,
                    "issues": [{
                        "issue": "Clinical accuracy evaluation failed - requires manual review",
                        "severity": "major",
                        "location": None,
                        "recommendation": "Manually verify clinical accuracy before proceeding"
                    }],
                    "evidence_gaps": [],
                    "summary": "Automatic clinical evaluation failed. Manual review required."
                },
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }

    
    # =========================================================================
    # NODE 3: TONE/EMPATHY CRITIC
    # =========================================================================
    def _tone_critic_node(self, state: CriticState) -> dict:
        """
        Tone/Empathy Critic - Ensures therapeutic alliance language.
        """
        self._emit("status", content="💚 Tone & Empathy Critic evaluating...")
        
        current_draft = state["current_draft"]
        plan = state.get("plan", {})
        
        # Get existing messages and scratchpad (for parallel execution merger)
        existing_messages = state.get("internal_messages") or []
        existing_scratchpad = state.get("internal_scratchpad") or ""
        
        # Extract tone-relevant info
        drafting_spec = plan.get("drafting_spec", {})
        style_rules = drafting_spec.get("style_rules", [])
        
        formatted_prompt = TONE_EMPATHY_CRITIC_PROMPT.format(
            style_rules=json.dumps(style_rules, indent=2) if style_rules else "None specified"
        )
        
        user_prompt = f"""## Draft to Evaluate:

{current_draft[:1500]}...

Evaluate this draft for tone, empathy, and therapeutic alliance."""
        
        # Track the message for Memory popup
        new_messages = [
            {"type": "SystemMessage", "content": "Tone & Empathy Critic Prompt"},
            {"type": "HumanMessage", "content": f"Style rules: {len(style_rules)} items"}
        ]
        
        # Track scratchpad entry
        scratchpad_entry = f"\n\n## 💚 Tone & Empathy Critic Analysis\n"
        scratchpad_entry += f"- Style rules evaluated: {len(style_rules)} items\n"
        
        try:
            tone_critique: ToneEmpathyCritique = self.tone_llm.invoke([
                SystemMessage(content=formatted_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            critique_dict = tone_critique.model_dump()
            
            # Build AI response for messages
            new_messages.append({
                "type": "AIMessage",
                "content": f"Tone Review: {'Approved' if critique_dict['approved'] else 'Issues Found'} (Score: {critique_dict['tone_score']}/10)\n\nSummary: {critique_dict['summary']}"
            })
            
            # Add to scratchpad
            scratchpad_entry += f"- Result: {'✅ Approved' if critique_dict['approved'] else '❌ Issues Found'}\n"
            scratchpad_entry += f"- Tone score: {critique_dict['tone_score']}/10\n"
            scratchpad_entry += f"- Issues: {len(critique_dict.get('issues', []))}\n"
            scratchpad_entry += f"- Summary: {critique_dict['summary']}\n"
            
            # Emit result
            status = "✅ Passed" if critique_dict["approved"] else f"❌ {len(critique_dict['issues'])} issues found"
            msg_content = f"**Tone & Empathy Review:** {status} (Score: {critique_dict['tone_score']}/10)\n{critique_dict['summary']}"
            self._emit("message_chunk", content=msg_content)
            self._emit("message_end")
            self._emit("message", content=msg_content)  # For persistence
            
            return {
                "tone_critique": critique_dict,
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }
            
        except Exception as e:
            self._emit("thought", content=f"⚠️ Tone evaluation error: {str(e)}")
            scratchpad_entry += f"- ERROR: {str(e)}\n"
            
            return {
                "tone_critique": {
                    "approved": True,  # Tone issues are less critical, don't block
                    "issues": [],
                    "tone_score": 5,
                    "summary": "Tone evaluation encountered an error. Proceeding with caution."
                },
                "internal_messages": existing_messages + new_messages,
                "internal_scratchpad": existing_scratchpad + scratchpad_entry
            }

    
    # =========================================================================
    # NODE 4: CONSOLIDATOR
    # =========================================================================
    def _consolidator_node(self, state: CriticState) -> dict:
        """
        Consolidates all 3 critic outputs into a unified critique document.
        """
        self._emit("status", content="📋 Consolidating critiques...")
        
        safety = state.get("safety_critique", {})
        clinical = state.get("clinical_critique", {})
        tone = state.get("tone_critique", {})
        iteration = state.get("iteration", 1)
        
        formatted_prompt = CONSOLIDATOR_PROMPT.format(
            safety_critique=json.dumps(safety, indent=2),
            clinical_critique=json.dumps(clinical, indent=2),
            tone_critique=json.dumps(tone, indent=2),
            iteration=iteration
        )
        
        try:
            # Build the consolidated critique
            consolidated: ConsolidatedCritique = self.consolidator_llm.invoke([
                SystemMessage(content=formatted_prompt),
                HumanMessage(content="Consolidate these critiques into a unified document with prioritized action items.")
            ])
            
            critique_dict = consolidated.model_dump()
            
            # Generate markdown for display
            critique_md = consolidated.to_markdown()
            
            
            
            # Emit summary message
            if critique_dict["overall_approved"]:
                msg_content = "✅ **Draft Approved!** All critics have approved the draft."
            else:
                action_count = len(critique_dict["action_items"])
                msg_content = f"❌ **Revision Needed:** {action_count} action items identified for improvement."
            self._emit("message_chunk", content=msg_content)
            self._emit("message_end")
            self._emit("message", content=msg_content)  # For persistence

            # Emit as artifact for canvas display
            self._emit(
                "artifact",
                content=critique_md,
                artifact_type="critique_document",
                title=f"Critique Report (Iteration {iteration})"
            )
            
            return {
                "consolidated_critique": critique_dict,
                "approved": critique_dict["overall_approved"]
            }
            
        except Exception as e:
            self._emit("thought", content=f"⚠️ Consolidation error: {str(e)}")
            # Manual consolidation fallback
            overall_approved = (
                safety.get("approved", False) and
                clinical.get("approved", False) and
                tone.get("approved", False)
            )
            
            return {
                "consolidated_critique": {
                    "overall_approved": overall_approved,
                    "iteration": iteration,
                    "safety": safety,
                    "clinical_accuracy": clinical,
                    "tone_empathy": tone,
                    "final_summary": "Automatic consolidation failed. Review individual critiques.",
                    "action_items": []
                },
                "approved": overall_approved
            }
    
    # =========================================================================
    # GRAPH CONSTRUCTION
    # =========================================================================
    def _build_graph(self) -> StateGraph:
        """
        Build and compile the critic subgraph.
        
        Architecture (PARALLEL):
            ┌─────────────────┐
            │   Entry Point   │
            └────────┬────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐
    │  Safety │ │Clinical │ │  Tone   │  ← Run in PARALLEL
    │  Critic │ │  Critic │ │  Critic │
    └────┬────┘ └────┬────┘ └────┬────┘
         │           │           │
         └───────────┼───────────┘
                     ▼
            ┌────────────────┐
            │  Consolidator  │  ← Waits for all 3
            └────────┬───────┘
                     ▼
                   [END]
        """
        
        graph = StateGraph(CriticState)
        
        # Add nodes
        graph.add_node("safety_critic", self._safety_critic_node)
        graph.add_node("clinical_critic", self._clinical_critic_node)
        graph.add_node("tone_critic", self._tone_critic_node)
        graph.add_node("consolidator", self._consolidator_node)
        
        # Set entry point - we'll use a fan-out pattern
        # Create parallel branches from START to all 3 critics
        graph.add_edge("__start__", "safety_critic")
        graph.add_edge("__start__", "clinical_critic")
        graph.add_edge("__start__", "tone_critic")
        
        # All 3 critics fan-in to consolidator
        graph.add_edge("safety_critic", "consolidator")
        graph.add_edge("clinical_critic", "consolidator")
        graph.add_edge("tone_critic", "consolidator")
        
        # Consolidator to END
        graph.add_edge("consolidator", END)
        
        return graph.compile()

    
    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================
    def invoke(self, state: dict) -> dict:
        """
        Execute the critic subgraph.
        
        Args:
            state: Input state with 'current_draft', 'plan', optionally 'protocol_contract'
            
        Returns:
            dict with 'critique_document' (markdown), 'critique_approved' (bool)
        """
        current_draft = state.get("current_draft") or state.get("draft", "")
        plan_str = state.get("plan", "{}")
        iteration = state.get("reflection_iteration", 1)
        
        # Emit agent_start event
        self._emit("agent_start", content=f"Evaluating draft with 3 specialized critics (iteration {iteration})...")
        
        # Parse plan if string
        try:
            plan = json.loads(plan_str) if isinstance(plan_str, str) else plan_str
        except json.JSONDecodeError:
            plan = {}
        
        # Initialize subgraph state
        initial_state: CriticState = {
            "current_draft": current_draft,
            "plan": plan,
            "protocol_contract": state.get("protocol_contract"),
            "iteration": iteration,
            "safety_critique": None,
            "clinical_critique": None,
            "tone_critique": None,
            "consolidated_critique": None,
            "approved": False,
            "internal_messages": [],
            "internal_scratchpad": f"# Critic Agent Analysis - Iteration {iteration}\n"
        }
        
        # Run the subgraph
        final_state = self.graph.invoke(initial_state)
        
        # Extract results
        consolidated = final_state.get("consolidated_critique", {})
        
        # Build markdown critique document
        try:
            critique_obj = ConsolidatedCritique(**consolidated)
            critique_md = critique_obj.to_markdown()
        except:
            critique_md = json.dumps(consolidated, indent=2)
        
        # Get accumulated messages and scratchpad from graph execution
        accumulated_messages = final_state.get("internal_messages") or []
        accumulated_scratchpad = final_state.get("internal_scratchpad") or ""
        
        # Add final consolidated decision to scratchpad
        accumulated_scratchpad += f"\n\n## 📋 Consolidated Decision\n"
        accumulated_scratchpad += f"- Overall Approved: {final_state.get('approved', False)}\n"
        accumulated_scratchpad += f"- Final Summary: {consolidated.get('final_summary', 'N/A')}\n"
        accumulated_scratchpad += f"- Action Items: {len(consolidated.get('action_items', []))}\n"
        
        # Emit agent memory with accumulated data
        self._emit(
            "agent_memory",
            messages=accumulated_messages,
            scratchpad=accumulated_scratchpad
        )
        
        return {
            "critique_document": critique_md,
            "critique_approved": final_state.get("approved", False),
            "critique_data": consolidated,  # Raw data for frontend
            "reflection_iteration": iteration
        }



# =============================================================================
# STANDALONE TEST
# =============================================================================
if __name__ == "__main__":
    print("Testing Critic Agent...")
    
    test_draft = """
# Graded Exposure Hierarchy for Social Anxiety

## Introduction
This exercise will help you gradually face social situations that cause anxiety.

## Steps
1. Start with low-anxiety situations (SUDS 20)
2. Practice breathing before each step
3. Move to medium situations (SUDS 50)
4. Challenge yourself with harder situations (SUDS 80)

## Reflection
After completing the hierarchy, notice how your anxiety changes over time.
"""
    
    test_plan = {
        "exercise_type": "Graded Exposure Hierarchy",
        "safety_envelope": {
            "forbidden_content": ["flooding", "trauma exposure"],
            "special_conditions": ["Include pacing reminder"]
        },
        "drafting_spec": {
            "style_rules": ["Use supportive tone", "Second-person voice"]
        },
        "critic_rubrics": {
            "clinical_accuracy": ["Proper SUDS progression", "Evidence-based steps"]
        }
    }
    
    critic = CriticAgent()
    result = critic.invoke({
        "current_draft": test_draft,
        "plan": json.dumps(test_plan),
        "reflection_iteration": 1
    })
    
    print("\n" + "="*60)
    print("CRITIQUE DOCUMENT:")
    print("="*60)
    print(result["critique_document"])
    print(f"\nApproved: {result['critique_approved']}")
