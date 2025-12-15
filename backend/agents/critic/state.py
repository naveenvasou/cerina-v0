"""
State TypedDict for Critic Agent subgraph.
"""

from typing import TypedDict, Optional, Dict, Any, List, Annotated
import operator


def add_messages(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reducer to merge message lists from parallel nodes."""
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right


def concat_strings(left: str, right: str) -> str:
    """Reducer to concatenate scratchpad strings from parallel nodes."""
    if left is None:
        left = ""
    if right is None:
        right = ""
    return left + right


class CriticState(TypedDict):
    """
    Internal state for the Critic Agent subgraph.
    """
    # Input from main graph
    current_draft: str                          # The draft to critique
    plan: Dict[str, Any]                        # Original plan for reference
    protocol_contract: Optional[Dict[str, Any]] # Protocol constraints from draftsman
    iteration: int                              # Current reflection iteration
    
    # Individual critic outputs
    safety_critique: Optional[Dict[str, Any]]
    clinical_critique: Optional[Dict[str, Any]]
    tone_critique: Optional[Dict[str, Any]]
    
    # Final output
    consolidated_critique: Optional[Dict[str, Any]]
    approved: bool
    
    # Memory tracking (for Memory popup) - use reducers for concurrent updates
    internal_messages: Annotated[List[Dict[str, Any]], add_messages]
    internal_scratchpad: Annotated[str, concat_strings]

