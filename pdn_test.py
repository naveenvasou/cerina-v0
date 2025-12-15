plan_output = {
        "exercise_type": "Sleep Hygiene Protocol (Component of CBT-I) for Insomnia",
        "drafting_spec": {
            "task_constraints": {
            "step_count": "Generate 8-12 distinct, actionable recommendations.",
            "progression_logic": "Recommendations should be grouped by clinical category (Environment, Lifestyle, Substances, Routine).",
            "focus_areas": "Must explicitly cover Environmental Setup, Substance Restriction (Caffeine/Alcohol), Napping Limits, Regular Exercise Timing, and Bed Use Restriction (Stimulus Control integration)."
            },
            "style_rules": [
            "Each recommendation must be stated as an explicit, measurable instruction (e.g., 'Ensure the bedroom temperature is cool and comfortable').",
            "Must include a brief clinical rationale for each step.",
            "The tone must be supportive, educational, and clinically grounded."
            ]
        },
        "safety_envelope": {
            "forbidden_content": [
            "Any statement suggesting sleep hygiene alone is the first-line, sufficient treatment for chronic insomnia.",
            "Prescription or dosage recommendations for sleep medications or supplements.",
            "Vague or unverifiable dietary or exercise advice."
            ],
            "special_conditions": [
            "The final output must include a prominent clinical disclaimer stating that for chronic insomnia, sleep hygiene is 'minimally effective as a stand-alone intervention' and must be integrated with core CBT-I components (Stimulus Control, Sleep Restriction). (Source: NBK526136)",
            "Must reinforce using the bed only for sleep and sex to align with Stimulus Control principles, a key component of CBT-I (Source: PMC6796223)."
            ]
        },
        "critic_rubrics": {
            "safety": [
            "Does the plan include the required clinical disclaimer regarding the limitations of sleep hygiene as a standalone treatment for chronic insomnia?",
            "Are all recommendations non-pharmacological and focused strictly on behavioral and environmental modification?",
            "Are the substance use guidelines (caffeine/alcohol) appropriately restrictive near bedtime?"
            ],
            "clinical_accuracy": [
            "Does the protocol accurately reflect the core components of sleep hygiene as defined by CBT-I guidelines (Environment, Lifestyle, Substance Use)? (Source: NBK526136)",
            "Is the instruction to limit the use of the bed for non-sleep activities clearly stated, integrating Stimulus Control principles? (Source: PMC6796223)",
            "Is the advice grounded in evidence (e.g., regular exercise, not close to bedtime)?"
            ],
            "usability": [
            "Are all recommendations clear, concise, and highly actionable for a patient?",
            "Are the recommendations organized logically by category?",
            "Is a brief rationale provided for each step to enhance patient understanding and adherence?"
            ]
        },
        "evidence_anchors": [
            {
            "source": "https://www.ncbi.nlm.nih.gov/books/NBK526136/",
            "note": "Confirms sleep hygiene is 'minimally effective as a stand-alone intervention' but an essential part of CBT-I, listing components like environmental setup, limiting napping, and restricting alcohol/caffeine."
            },
            {
            "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6796223/",
            "note": "Outlines the five key components of CBT-I, emphasizing the integration of behavioral elements like Stimulus Control (using the bed only for sleeping and sex) alongside sleep hygiene."
            },
            {
            "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7853203/",
            "note": "Stresses that clinical resources should be devoted to CBT-I or BTIs rather than providing sleep hygiene alone, due to lack of evidence for its single-component efficacy."
            }
        ],
        "user_preview": "We will generate a structured, evidence-based Sleep Hygiene Protocol. This plan will provide specific guidance on environmental adjustments, lifestyle changes (diet, exercise, substances), and behavioral rules to optimize your sleep quality, framed within the principles of Cognitive Behavioral Therapy for Insomnia (CBT-I)."
        }


# Test script - import and call the actual method
import json
from backend.agents.draftsman.agent import DraftsmanAgent


def test_protocol_decomposition():
    """Test the protocol decomposition node directly."""
    
    print("=" * 60)
    print("Testing Protocol Decomposition Node")
    print("=" * 60)
    
    # Create the agent
    agent = DraftsmanAgent()
    
    # Build initial state
    state = {
        "planner_output": plan_output,
        "protocol_contract": None,
        "mechanism_map": None,
        "exercise_skeleton": None,
        "current_section_index": 0,
        "drafted_sections": {},
        "draft_v0": None,
        "assembled_markdown": None,
        "final_draft": None,
        "iteration_count": 0
    }
    
    # Call the node directly
    result = agent._protocol_decomposition_node(state)
    
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    test_protocol_decomposition()
