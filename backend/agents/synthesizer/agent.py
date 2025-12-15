"""
Presentation Synthesizer Agent - Final formatting pass.

Takes an approved draft and produces a polished, patient-ready document
with optimal formatting, scannability, and visual presentation.
"""

import json
import re
from datetime import datetime
from typing import Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from backend.settings import settings
from backend.events import get_emitter

from backend.agents.synthesizer.prompts import PRESENTATION_SYNTHESIZER_PROMPT


def extract_markdown_from_codeblock(content: str) -> str:
    """
    Extract markdown content from code block wrappers if present.
    
    LLMs sometimes wrap their output in ```markdown ... ``` or ``` ... ```
    This function extracts the actual content.
    """
    if not content:
        return content
    
    # Pattern to match ```markdown ... ``` or ```md ... ``` or ``` ... ```
    patterns = [
        r'^```(?:markdown|md)?\s*\n(.*?)\n```\s*$',  # Full wrap
        r'^```(?:markdown|md)?\s*\n(.*)',             # Only opening
        r'(.*?)\n```\s*$',                            # Only closing
    ]
    
    # Try the full match first
    full_match = re.match(r'^```(?:markdown|md)?\s*\n(.*?)\n```\s*$', content, re.DOTALL)
    if full_match:
        return full_match.group(1).strip()
    
    # Check if content starts with code block but doesn't end properly
    if content.strip().startswith('```'):
        lines = content.strip().split('\n')
        # Remove first line if it's just the code block opener
        if lines[0].strip() in ['```', '```markdown', '```md']:
            lines = lines[1:]
        # Remove last line if it's just the code block closer
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        return '\n'.join(lines).strip()
    
    return content.strip()



class PresentationSynthesizerAgent:
    """
    Presentation Synthesizer Agent.
    
    Final formatting pass that:
    - Reorganizes content for optimal readability
    - Compresses verbose sections
    - Adds visual polish (tables, bullets, emphasis)
    - Produces patient-ready Markdown
    
    Does NOT modify clinical content - only presentation.
    """
    
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.2
    ):
        """
        Initialize the Presentation Synthesizer.
        
        Args:
            model: LLM model for synthesis
            temperature: Low temperature for faithful formatting
        """
        self.synthesizer_llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature,
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
                emitter.emit_thought("synthesizer", kwargs.get("content", ""))
            elif event_type == "thought_chunk":
                emitter.emit_thought_chunk("synthesizer", kwargs.get("content", ""))
            elif event_type == "message_chunk":
                emitter.emit_message_chunk("synthesizer", kwargs.get("content", ""))
            elif event_type == "message_end":
                emitter.emit_message_end("synthesizer")
            elif event_type == "status":
                emitter.emit_status("synthesizer", kwargs.get("content", ""))
            elif event_type == "artifact":
                emitter.emit_artifact(
                    "synthesizer",
                    kwargs.get("content", ""),
                    kwargs.get("artifact_type", ""),
                    kwargs.get("title", "")
                )
            elif event_type == "agent_memory":
                emitter.emit_agent_memory(
                    "Presentation Synthesizer",
                    kwargs.get("messages", []),
                    kwargs.get("scratchpad", "")
                )
            elif event_type == "agent_start":
                emitter.emit_agent_start("Presentation Synthesizer", kwargs.get("content", ""))
    
    # =========================================================================
    # SYNTHESIS LOGIC
    # =========================================================================
    def _synthesize(self, draft: str, plan: Dict[str, Any]) -> str:
        """
        Apply final presentation formatting to the draft.
        
        Returns the synthesized/formatted content.
        """
        exercise_type = plan.get("exercise_type", "CBT Exercise")
        
        # Extract protocol constraints
        protocol_constraints = json.dumps({
            "forbidden_content": plan.get("safety_envelope", {}).get("forbidden_content", []),
            "required_components": plan.get("drafting_spec", {}).get("required_fields", []),
        }, indent=2)
        
        formatted_prompt = PRESENTATION_SYNTHESIZER_PROMPT.format(
            protocol_constraints=protocol_constraints,
            draft=draft,
            exercise_type=exercise_type
        )
        
        # Stream the synthesis for real-time visibility
        accumulated_content = ""
        
        for chunk in self.synthesizer_llm.stream([
            SystemMessage(content=formatted_prompt),
            HumanMessage(content="Reformat this draft for optimal patient presentation. Output only the formatted Markdown.")
        ]):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                accumulated_content += content
        
        return accumulated_content if accumulated_content else draft
    
    # =========================================================================
    # PUBLIC INTERFACE
    # =========================================================================
    def invoke(self, state: dict) -> dict:
        """
        Execute the presentation synthesis.
        
        Args:
            state: Input state with 'current_draft' (approved), 'plan'
            
        Returns:
            dict with 'final_presentation', 'draft' (final)
        """
        # Emit agent_start event first
        self._emit("agent_start", content="Draft approved! Applying final presentation formatting...")
        
        self._emit("thought", content="Applying final formatting: structure optimization, compression, scannability polish...")
        
        # Get the approved draft
        current_draft = state.get("current_draft") or state.get("draft", "")
        plan_str = state.get("plan", "{}")
        draft_versions = state.get("draft_versions", [])
        
        # Parse plan if string
        try:
            plan = json.loads(plan_str) if isinstance(plan_str, str) else plan_str
        except json.JSONDecodeError:
            plan = {}
        
        exercise_type = plan.get("exercise_type", "CBT Exercise")
        
        # Perform synthesis
        final_presentation = self._synthesize(current_draft, plan)
        
        # Create final version entry
        final_version = {
            "version": len(draft_versions) + 1,
            "content": final_presentation,
            "timestamp": datetime.now().isoformat(),
            "status": "final",
            "iteration": state.get("reflection_iteration", 1),
            "changes": "Final presentation formatting applied"
        }
        
        updated_versions = list(draft_versions) + [final_version]
        
        # Emit completion message
        self._emit("message_chunk", content=f"✅ **Final Presentation Ready**\n\nYour {exercise_type} has been synthesized and is ready for use.")
        self._emit("message_end")

        # Emit the final artifact
        self._emit(
            "artifact",
            content=final_presentation,
            artifact_type="cbt_exercise",
            title=f"CBT Exercise: {exercise_type}"
        )
        
        # Build messages for Memory popup
        memory_messages = [
            {"type": "SystemMessage", "content": "Presentation Synthesizer Prompt - Apply final formatting and polish"},
            {"type": "HumanMessage", "content": f"Draft to synthesize: {exercise_type}\nDraft length: {len(current_draft)} characters"},
            {"type": "AIMessage", "content": f"Synthesis complete. Created final version v{final_version['version']}.\n\nApplied formatting:\n- Structure optimization\n- Scannability polish\n- Patient-ready presentation"}
        ]
        
        # Build scratchpad for Memory popup
        scratchpad = f"# Presentation Synthesizer - Final Pass\n\n"
        scratchpad += f"## Exercise Type\n{exercise_type}\n\n"
        scratchpad += f"## Processing\n"
        scratchpad += f"- Input draft length: {len(current_draft)} characters\n"
        scratchpad += f"- Output length: {len(final_presentation)} characters\n"
        scratchpad += f"- Compression ratio: {len(final_presentation)/max(len(current_draft), 1):.1%}\n\n"
        scratchpad += f"## Formatting Applied\n"
        scratchpad += f"- Structure optimization\n"
        scratchpad += f"- Compression\n"
        scratchpad += f"- Scannability polish\n"
        scratchpad += f"- Patient-ready formatting\n\n"
        scratchpad += f"## Version Created\n"
        scratchpad += f"- Version: v{final_version['version']}.0 (Final)\n"
        
        # Emit agent memory with messages
        self._emit(
            "agent_memory",
            messages=memory_messages,
            scratchpad=scratchpad
        )
        
        return {
            "final_presentation": final_presentation,
            "draft": final_presentation,  # Update main draft to final
            "current_draft": final_presentation,
            "draft_versions": updated_versions
        }



# =============================================================================
# STANDALONE TEST
# =============================================================================
if __name__ == "__main__":
    print("Testing Presentation Synthesizer Agent...")
    
    test_draft = """
# Graded Exposure Hierarchy for Social Anxiety

## Introduction

Social anxiety can make everyday situations feel overwhelming. This exercise will help you gradually build confidence by facing situations step by step. Remember, you're in control of the pace.

## Step 1: Low Anxiety Situations (SUDS 20-30)

Start with situations that cause mild discomfort. Practice these until your anxiety decreases by at least half.

- Make eye contact with a stranger briefly
- Ask a store clerk a simple question
- Say hello to a neighbor

## Step 2: Medium Anxiety Situations (SUDS 40-50)

Once Step 1 feels manageable, move to these moderate challenges.

- Join a brief conversation at work
- Make a phone call to schedule an appointment
- Attend a small social gathering for 30 minutes

## Step 3: Higher Anxiety Situations (SUDS 60-70)

Challenge yourself with these more demanding situations.

- Give a brief opinion in a meeting
- Initiate a conversation with someone new
- Attend a networking event

## Reflection

After each practice session, take a moment to notice:
- What was your peak anxiety level?
- Did it decrease as you stayed in the situation?
- What did you learn about your ability to cope?
"""
    
    test_plan = {
        "exercise_type": "Graded Exposure Hierarchy for Social Anxiety",
        "safety_envelope": {"forbidden_content": ["flooding"]},
        "drafting_spec": {"required_fields": ["SUDS ratings", "grounding techniques"]}
    }
    
    synthesizer = PresentationSynthesizerAgent()
    result = synthesizer.invoke({
        "current_draft": test_draft,
        "plan": json.dumps(test_plan)
    })
    
    print("\n" + "="*60)
    print("FINAL PRESENTATION:")
    print("="*60)
    print(result["final_presentation"])
