"""
State schema for the Deterministic Drafting Subgraph.

Supports the sequential section drafting loop with explicit stage tracking.
"""

from typing import TypedDict, Optional, Dict, Any


class DraftsmanState(TypedDict):
    """
    State schema for the Deterministic Drafting Subgraph.
    
    This state flows through 6 sequential stages:
    1. protocol_decomposition → protocol_contract
    2. mechanism_mapper → mechanism_map
    3. skeleton_agent → exercise_skeleton
    4. section_draft (loop) → drafted_sections
    5. draft_assembler → draft_v0
    6. presentation_synthesizer → final_draft
    """
    
    
    planner_output: dict  # Full PlanOutput as dict (exercise_type, drafting_spec, safety_envelope, etc.)
    
    protocol_contract: Optional[dict]  # ProtocolContract as dict
    
    mechanism_map: Optional[dict]  # MechanismMap as dict
    
    exercise_skeleton: Optional[dict]  # ExerciseSkeleton as dict
    
    current_section_index: int  # Index into exercise_skeleton.sections
    drafted_sections: Dict[str, str]  # {section_id: content} - accumulated drafts
    
    
    draft_v0: Optional[dict]  # DraftV0 as dict (raw assembled draft)
    assembled_markdown: Optional[str]  # Raw markdown before presentation pass
    
    final_draft: Optional[str]  # Final formatted markdown (ready for display)
    
    # METADATA
    iteration_count: int  # Safety counter for the section loop

