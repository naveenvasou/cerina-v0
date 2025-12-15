from typing import List, Dict
from pydantic import BaseModel, Field

# =============================================================================
# OUTPUT SCHEMAS (Pydantic) - Nested Models for Structured Output
# =============================================================================

class DraftingSpec(BaseModel):
    """Specification for the drafting agent with explicit structure."""
    task_constraints: Dict[str, str] = Field(
        description="Key constraints like step_count, progression_logic, focus_areas as key-value pairs"
    )
    style_rules: List[str] = Field(
        description="Style guidelines for the draft (e.g., 'Steps must be specific and measurable')"
    )


class SafetyEnvelope(BaseModel):
    """Safety constraints for the clinical plan with explicit structure."""
    forbidden_content: List[str] = Field(
        description="Content that must NOT appear in the draft"
    )
    special_conditions: List[str] = Field(
        description="Special safety conditions or guardrails to include"
    )


class CriticRubrics(BaseModel):
    """Rubrics for the critic panel to evaluate the draft with explicit categories."""
    safety: List[str] = Field(
        description="Safety-related constraints specific to this exercise type"
    )
    clinical_accuracy: List[str] = Field(
        description="Clinical accuracy constraints based on the protocol"
    )
    usability: List[str] = Field(
        description="Usability/user experience constraints"
    )


class EvidenceAnchor(BaseModel):
    """A single evidence anchor for the clinical plan."""
    source: str = Field(description="Citation source (e.g., 'Craske et al., 2014')")
    note: str = Field(description="Brief note on the relevance of this source")


class PlanOutput(BaseModel):
    """
    Structured output schema for the clinical protocol specification.
    
    Uses nested Pydantic models to enforce the exact output structure
    required by downstream agents (Draftsman, Critics).
    """
    exercise_type: str = Field(
        description="The identified CBT exercise type with specificity (e.g., 'Exposure Hierarchy (In Vivo) for Agoraphobia')"
    )
    drafting_spec: DraftingSpec = Field(
        description="Detailed specification for the drafting agent"
    )
    safety_envelope: SafetyEnvelope = Field(
        description="Safety constraints and forbidden content"
    )
    critic_rubrics: CriticRubrics = Field(
        description="Evaluation rubrics for the critic panel"
    )
    evidence_anchors: List[EvidenceAnchor] = Field(
        min_length=2,
        max_length=3,
        description="2-3 evidence citations grounded in clinical literature from tool outputs"
    )
    user_preview: str = Field(
        description="A brief, friendly preview message describing what will be created"
    )
