"""
ID Generator Utility

Generates prefixed alphanumeric IDs for database entities.
Uses cryptographically secure random generation.
"""

import secrets
import string


def generate_id(prefix: str, length: int = 10) -> str:
    """
    Generate a prefixed alphanumeric ID.
    
    Args:
        prefix: The prefix for the ID (e.g., "SES_", "MSG_")
        length: Length of the random part (default 10)
    
    Returns:
        A string like "SES_7xK9mN2pQ4"
    
    Examples:
        >>> generate_id("SES_")
        'SES_7xK9mN2pQ4'
        >>> generate_id("MSG_", 12)
        'MSG_3fR8tY5wL1Km'
    """
    chars = string.ascii_letters + string.digits  # a-z, A-Z, 0-9 (62 chars)
    random_part = ''.join(secrets.choice(chars) for _ in range(length))
    return f"{prefix}{random_part}"


# Convenience functions for each entity type
def generate_session_id() -> str:
    return generate_id("SES_")


def generate_workflow_run_id() -> str:
    return generate_id("WRK_")


def generate_message_id() -> str:
    return generate_id("MSG_")


def generate_artifact_id() -> str:
    return generate_id("ART_")


def generate_event_id() -> str:
    return generate_id("EVT_")


def generate_memory_id() -> str:
    return generate_id("MEM_")


def generate_chat_history_id() -> str:
    return generate_id("CHT_")
