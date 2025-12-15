"""
Critic Agent Module

Multi-perspective critique agent with 3 specialized critics:
1. Safety Critic - Checks for harmful content, flooding, contraindications
2. Clinical Accuracy Critic - Validates evidence-based practices  
3. Tone/Empathy Critic - Ensures therapeutic alliance language
"""

from backend.agents.critic.agent import CriticAgent

__all__ = ["CriticAgent"]
