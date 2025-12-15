"""
Reviser Agent - Revises drafts based on critique feedback.

Takes the current draft and critique document, applies targeted edits
to address identified issues while preserving clinical integrity.
"""

import json
from datetime import datetime
from typing import Dict, Any, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.settings import settings
from backend.events import get_emitter

from backend.agents.reviser.state import ReviserState
from backend.agents.reviser.prompts import REVISER_PROMPT, REVISION_SUMMARY_PROMPT


class ReviserAgent:
    """
    Reviser Agent that applies critique feedback to improve drafts.
    
    Key behaviors:
    - Surgical edits: Only modify flagged sections
    - Version tracking: Creates new version with metadata
    - Constraint adherence: Never violates protocol constraints
    """
    
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.4
    ):
        """
        Initialize the Reviser Agent.
        
        Args:
            model: LLM model for revision
            temperature: Moderate temperature for creative but controlled edits
        """
        self.reviser_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
            google_api_key=settings.GEMINI_API_KEY,
        )
        
        # Lower temperature for summary generation
        self.summary_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0.2,
            google_api_key=settings.GEMINI_API_KEY,
        )
    
    # =========================================================================
    # EVENT EMISSION HELPERS
    # =========================================================================
    def _emit(self, event_type: str, **kwargs):
        """Emit event if emitter is available."""
        emitter = get_emitter()
        if emitter:
            if event_type == "thought":
                emitter.emit_thought("reviser", kwargs.get("content", ""))
            elif event_type == "thought_chunk":
                emitter.emit_thought_chunk("reviser", kwargs.get("content", ""))
            elif event_type == "message_chunk":
                emitter.emit_message_chunk("reviser", kwargs.get("content", ""))
            elif event_type == "message_end":
                emitter.emit_message_end("reviser")
            elif event_type == "message":
                emitter.emit_message("reviser", kwargs.get("content", ""))
            elif event_type == "status":
                emitter.emit_status("reviser", kwargs.get("content", ""))
            elif event_type == "artifact":
                emitter.emit_artifact(
                    "reviser",
                    kwargs.get("content", ""),
                    kwargs.get("artifact_type", ""),
                    kwargs.get("title", "")
                )
            elif event_type == "agent_memory":
                emitter.emit_agent_memory(
                    "Reviser Agent",
                    kwargs.get("messages", []),
                    kwargs.get("scratchpad", "")
                )
            elif event_type == "agent_start":
                emitter.emit_agent_start("Reviser Agent", kwargs.get("content", ""))
    
    # =========================================================================
    # REVISION LOGIC
    # =========================================================================
    def _revise_draft(self, state: ReviserState) -> str:
        """
        Apply revisions to the draft based on critique.
        
        Returns the revised draft content.
        """
        current_draft = state["current_draft"]
        critique_document = state.get("critique_document", "")
        critique_data = state.get("critique_data", {})
        plan = state.get("plan", {})
        protocol_contract = state.get("protocol_contract", {})
        
        # Extract action items from critique
        action_items = critique_data.get("action_items", [])
        if not action_items:
            # Try to extract from the markdown critique
            action_items = ["Review and address all issues mentioned in the critique document"]
        
        # Format protocol constraints
        protocol_constraints = json.dumps({
            "forbidden_content": plan.get("safety_envelope", {}).get("forbidden_content", []),
            "required_components": plan.get("drafting_spec", {}).get("required_fields", []),
            "style_rules": plan.get("drafting_spec", {}).get("style_rules", [])
        }, indent=2)
        
        # Format the revision prompt
        formatted_prompt = REVISER_PROMPT.format(
            protocol_constraints=protocol_constraints,
            critique_document=critique_document,
            action_items="\n".join(f"- {item}" for item in action_items),
            current_draft=current_draft
        )
        
        self._emit("message_chunk", content=f"Applying {len(action_items)} revision action items...")
        self._emit("message_end")
        self._emit("message", content=f"Applying {len(action_items)} revision action items...")  # For persistence
        
        # Stream the revision for real-time visibility
        accumulated_content = ""
        
        for chunk in self.reviser_llm.stream([
            SystemMessage(content=formatted_prompt),
            HumanMessage(content="Produce the revised draft now. Output only the improved Markdown content.")
        ]):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                accumulated_content += content
        
        return accumulated_content if accumulated_content else current_draft
    
    def _generate_revision_summary(
        self,
        original_draft: str,
        revised_draft: str,
        action_items: List[str]
    ) -> str:
        """Generate a brief summary of changes made."""
        try:
            formatted_prompt = REVISION_SUMMARY_PROMPT.format(
                original_draft=original_draft[:2000],  # Truncate for context
                revised_draft=revised_draft[:2000],
                action_items="\n".join(f"- {item}" for item in action_items)
            )
            
            response = self.summary_llm.invoke([
                SystemMessage(content=formatted_prompt),
                HumanMessage(content="Summarize the key changes in 3-5 bullet points.")
            ])
            
            return response.content if hasattr(response, 'content') else str(response)
        except:
            return "Revision applied based on critique feedback."
    
    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================
    def invoke(self, state: dict) -> dict:
        """
        Execute the revision process.
        
        Args:
            state: Input state with 'current_draft', 'critique_document', 'plan'
            
        Returns:
            dict with 'current_draft' (revised), 'draft_versions' (updated list)
        """
        
        current_draft = state.get("current_draft") or state.get("draft", "")
        
        # Emit agent_start event
        iteration = state.get("reflection_iteration", 1)
        self._emit("agent_start", content=f"Revising draft based on critique (iteration {iteration})...")
        
        critique_document = state.get("critique_document", "")
        critique_data = state.get("critique_data", {})
        plan_str = state.get("plan", "{}")
        iteration = state.get("reflection_iteration", 1)
        draft_versions = state.get("draft_versions", [])
        
        # Parse plan if string
        try:
            plan = json.loads(plan_str) if isinstance(plan_str, str) else plan_str
        except json.JSONDecodeError:
            plan = {}
        
        # Build internal state
        reviser_state: ReviserState = {
            "current_draft": current_draft,
            "critique_document": critique_document,
            "critique_data": critique_data,
            "plan": plan,
            "protocol_contract": state.get("protocol_contract"),
            "revised_draft": None,
            "revision_notes": None
        }
        
        # Perform revision
        revised_draft = self._revise_draft(reviser_state)
        
        # Generate revision summary
        action_items = critique_data.get("action_items", [])
        revision_summary = self._generate_revision_summary(
            current_draft, revised_draft, action_items
        )
        
        # Create new version entry
        new_version = {
            "version": len(draft_versions) + 1,
            "content": revised_draft,
            "timestamp": datetime.now().isoformat(),
            "status": "revised",
            "iteration": iteration,
            "changes": revision_summary
        }
        
        # Append to version history
        updated_versions = list(draft_versions) + [new_version]
        
        # Emit the revised draft as artifact
        self._emit(
            "artifact",
            content=revised_draft,
            artifact_type="draft_revision",
            title=f"Revised Draft (v{new_version['version']})"
        )
        
        # Emit summary message
        msg_content = f"**Revision Complete (v{new_version['version']})**\n\n{revision_summary}"
        self._emit("message_chunk", content=msg_content)
        self._emit("message_end")
        self._emit("message", content=msg_content)  # For persistence
        
        # Build messages for Memory popup
        memory_messages = [
            {"type": "SystemMessage", "content": "Reviser Prompt - Apply critique feedback to improve draft"},
            {"type": "HumanMessage", "content": f"Action items to apply: {len(action_items)} items\n\nCritique summary: {critique_document[:300]}..."},
            {"type": "AIMessage", "content": f"Revision complete. Created v{new_version['version']}.\n\nChanges made:\n{revision_summary}"}
        ]
        
        # Build scratchpad for Memory popup
        scratchpad = f"# Reviser Agent - Iteration {iteration}\n\n"
        scratchpad += f"## Action Items Applied ({len(action_items)})\n"
        for item in action_items:
            scratchpad += f"- {item}\n"
        scratchpad += f"\n## Revision Summary\n{revision_summary}\n"
        scratchpad += f"\n## Version Created\n- Version: v{new_version['version']}\n- Status: {new_version['status']}\n"
        
        # Emit agent memory with messages
        self._emit(
            "agent_memory",
            messages=memory_messages,
            scratchpad=scratchpad
        )
        
        # Increment iteration for next loop
        return {
            "current_draft": revised_draft,
            "draft": revised_draft,  # Also update main draft field
            "draft_versions": updated_versions,
            "reflection_iteration": iteration + 1,
            "revision_notes": revision_summary
        }



# =============================================================================
# STANDALONE TEST
# =============================================================================
if __name__ == "__main__":
    print("Testing Reviser Agent...")
    
    test_draft = """
# Graded Exposure Hierarchy for Social Anxiety

## Introduction
This exercise will help you face social situations.

## Steps
1. Start with low situations
2. Move to harder ones
3. Complete the hierarchy

## Reflection
Think about your progress.
"""
    
    test_critique = """
# Critique Report

## Action Items
1. Add SUDS ratings to each step
2. Include grounding techniques
3. Expand the introduction with psychoeducation
4. Add warmth and validation
"""
    
    test_plan = {
        "exercise_type": "Graded Exposure Hierarchy",
        "safety_envelope": {"forbidden_content": ["flooding"]},
        "drafting_spec": {"style_rules": ["Supportive tone"]}
    }
    
    reviser = ReviserAgent()
    result = reviser.invoke({
        "current_draft": test_draft,
        "critique_document": test_critique,
        "critique_data": {
            "action_items": [
                "Add SUDS ratings to each step",
                "Include grounding techniques",
                "Expand introduction",
                "Add warmth"
            ]
        },
        "plan": json.dumps(test_plan),
        "reflection_iteration": 1
    })
    
    print("\n" + "="*60)
    print("REVISED DRAFT:")
    print("="*60)
    print(result["current_draft"])
    print(f"\nVersion: {result['draft_versions'][-1]['version']}")
