"""
Pydantic schemas for the Deterministic Drafting Subgraph.

This module defines all structured outputs for the 5-agent pipeline:
1. ProtocolDecompositionAgent → ProtocolContract
2. TherapeuticMechanismMapper → MechanismMap
3. ExerciseSkeletonAgent → ExerciseSkeleton
4. SectionDraftAgent → SectionDraft
5. DraftAssembler → DraftV0
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# =============================================================================
# 1. PROTOCOL CONTRACT (from Protocol Decomposition Agent)
# =============================================================================

class ProtocolContract(BaseModel):
    """
    Hard constraints that drafting must not violate.
    Extracted from planner output by Protocol Decomposition Agent.
    """
    protocol_invariants: List[str] = Field(
        description="Non-negotiable clinical rules that must be followed (e.g., 'SUDS ratings must use 0-100 scale')"
    )
    required_components: List[str] = Field(
        description="Mandatory components that must appear in the exercise (e.g., 'Safety disclaimer', 'Progressive steps')"
    )
    forbidden_moves: List[str] = Field(
        description="Therapeutic moves that are explicitly forbidden (e.g., 'No flooding without consent')"
    )
    allowed_flexibility: List[str] = Field(
        description="Elements where drafting has creative freedom (e.g., 'Wording of prompts', 'Number of examples')"
    )


# =============================================================================
# 2. MECHANISM MAP (from Therapeutic Mechanism Mapper)
# =============================================================================

class TargetMechanism(BaseModel):
    """A single psychological mechanism to be addressed by the exercise."""
    mechanism: str = Field(
        description="The psychological mechanism being targeted (e.g., 'Inhibitory learning', 'Cognitive restructuring')"
    )
    maladaptive_belief: str = Field(
        description="The maladaptive belief or pattern being addressed (e.g., 'I cannot handle public speaking')"
    )
    maintaining_behaviors: List[str] = Field(
        description="Behaviors that maintain the problem (e.g., ['Avoidance', 'Safety behaviors', 'Reassurance seeking'])"
    )
    learning_goal: str = Field(
        description="What the patient should learn/experience (e.g., 'Anxiety decreases naturally without escape')"
    )


class MechanismMap(BaseModel):
    """
    Explicit model of psychological learning required for the exercise to work.
    This is the causal core of the system.
    """
    target_mechanisms: List[TargetMechanism] = Field(
        min_length=1,
        description="Psychological mechanisms being targeted"
    )
    required_learning_signals: List[str] = Field(
        description="Learning signals the exercise must create (e.g., 'Expectancy violation', 'Disconfirmation')"
    )
    behavioral_requirements: List[str] = Field(
        description="Behavioral requirements for learning (e.g., 'Remain in situation until anxiety peaks and declines')"
    )


# =============================================================================
# 3. EXERCISE SKELETON (from Exercise Skeleton Agent)
# =============================================================================

class SectionConstraints(BaseModel):
    """Constraints for a single section."""
    max_length: Optional[str] = Field(
        default=None,
        description="Maximum length constraint (e.g., '3 paragraphs', '200 words')"
    )
    tone: Optional[str] = Field(
        default=None,
        description="Required tone (e.g., 'Warm and supportive', 'Direct and clinical')"
    )
    format: Optional[str] = Field(
        default=None,
        description="Required format (e.g., 'Numbered list', 'Free text with prompts')"
    )


class SectionSpec(BaseModel):
    """Specification for a single section in the exercise skeleton."""
    section_id: str = Field(
        description="Unique identifier for the section (e.g., 'introduction', 'step_1', 'reflection')"
    )
    purpose: str = Field(
        description="Clinical purpose of this section (e.g., 'Orient patient to the exercise and set expectations')"
    )
    required_elements: List[str] = Field(
        description="Elements that must appear in this section (e.g., ['SUDS anchor points', 'Time estimation'])"
    )
    constraints: SectionConstraints = Field(
        default_factory=SectionConstraints,
        description="Structural constraints for this section"
    )


class ExerciseSkeleton(BaseModel):
    """
    Frozen structural blueprint for the exercise.
    Prevents structural hallucination by defining all sections upfront.
    """
    sections: List[SectionSpec] = Field(
        min_length=1,
        description="Ordered list of sections that make up the exercise"
    )


# =============================================================================
# 4. SECTION DRAFT (from Section Draft Agent - per iteration)
# =============================================================================

class SectionDraft(BaseModel):
    """Output from a single section drafting iteration."""
    section_id: str = Field(
        description="ID of the section being drafted (must match skeleton)"
    )
    section_content: str = Field(
        description="The actual drafted content for this section (Markdown)"
    )


# =============================================================================
# 5. DRAFT V0 (Final Output from Draft Assembler)
# =============================================================================

class DraftV0(BaseModel):
    """
    Final assembled draft artifact.
    Contains both the exercise content and full metadata for traceability.
    """
    exercise: Dict[str, str] = Field(
        description="Ordered sections as {section_id: content}"
    )
    metadata: Dict[str, Any] = Field(
        description="Full metadata including protocol_contract, mechanism_map, and skeleton"
    )


# =============================================================================
# LEGACY COMPATIBILITY (for gradual migration if needed)
# =============================================================================

class QueryPrompt(BaseModel):
    """DEPRECATED: Legacy schema from fan-out architecture."""
    name: str = Field(description="Short identifier for this query")
    prompt: str = Field(description="The query prompt text")


class ContextFragment(BaseModel):
    """DEPRECATED: Legacy schema from fan-out architecture."""
    query_name: str = Field(description="Name of the query")
    content: str = Field(description="The extracted content")
    confidence: float = Field(default=0.9)


class DispatcherOutput(BaseModel):
    """DEPRECATED: Legacy schema from fan-out architecture."""
    query_prompts: List[QueryPrompt] = Field(min_length=1, max_length=10)


class DraftOutput(BaseModel):
    """DEPRECATED: Legacy schema from fan-out architecture."""
    title: str
    exercise_type: str
    content_markdown: str
    queries_used: List[str]
