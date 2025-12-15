"""
State TypedDict for Reviser Agent.
"""

from typing import TypedDict, Optional, Dict, Any, List


class ReviserState(TypedDict):
    """
    Internal state for the Reviser Agent.
    """
    # Input
    current_draft: str                          # Draft to revise
    critique_document: str                      # Markdown critique from critic
    critique_data: Optional[Dict[str, Any]]     # Structured critique data
    plan: Dict[str, Any]                        # Original plan for constraints
    protocol_contract: Optional[Dict[str, Any]] # Protocol constraints
    
    # Output
    revised_draft: Optional[str]                # The revised draft
    revision_notes: Optional[str]               # Notes about what was changed
