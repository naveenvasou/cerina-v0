"""
DraftsmanAgent - Deterministic 6-Stage Drafting Subgraph

Pipeline:
1. ProtocolDecompositionAgent → protocol_contract
2. TherapeuticMechanismMapper → mechanism_map  
3. ExerciseSkeletonAgent → exercise_skeleton
4. SectionDraftAgent (loop) → drafted_sections
5. DraftAssembler (non-LLM) → draft_v0
6. PresentationSynthesizer (LLM) → final_draft
"""

from backend.agents.draftsman.agent import DraftsmanAgent

__all__ = ["DraftsmanAgent"]
