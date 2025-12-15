import os
import json
from typing import Dict, List, Optional, Type
from langchain_core.tools import BaseTool
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from backend.settings import settings

# Set Tavily API key in environment (required by langchain)
if settings.TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = settings.TAVILY_API_KEY

# --- Tool Input Schemas ---

class SearchInput(BaseModel):
    query: str = Field(description="The clinical topic or protocol to search for (e.g., 'CBT protocols for insomnia').")

class SafetyCheckInput(BaseModel):
    plan_overview: str = Field(description="A summary of the proposed clinical intervention plan.")
    risk_factors: str = Field(description="List of user's potential risk factors (e.g., 'history of trauma', 'suicidal ideation'). If none, say 'None'.")

# --- Clinical Search Tool ---

class ClinicalSearchTool(BaseTool):
    name: str = "search_clinical_protocols"
    description: str = "Search for evidence-based clinical protocols and guidelines. Use this to find validated CBT techniques."
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str) -> str:
        """Executes a search using Tavily API with clinical domain filtering."""
        try:
            # Check for API Key
            if not settings.TAVILY_API_KEY:
                return "[Mock Search Result] TAVILY_API_KEY not configured. Returning mock data for: " + query + "\n\nRecommended Protocol: Standard CBT protocol with psychoeducation, cognitive restructuring, and behavioral experiments. Source: APA Guidelines."

            # Initialize Tavily
            search = TavilySearchResults(
                max_results=3,
                search_depth="advanced",
                include_domains=[
                    "nih.gov", 
                    "apa.org", 
                    "mayoclinic.org", 
                    "psychologytools.com",
                    "ncbi.nlm.nih.gov"
                ]
            )
            
            results = search.invoke({"query": query})
            
            # Format results
            formatted_results = []
            for res in results:
                formatted_results.append(f"Source: {res['url']}\nContent: {res['content']}")
            
            return "\n\n".join(formatted_results) if formatted_results else "No clinical protocols found for this query."

        except Exception as e:
            return f"Search failed: {str(e)}"

# --- Safety Adversary Tool (LLM Guardrail) ---

class SafetyAdversaryTool(BaseTool):
    name: str = "check_safety_constraints"
    description: str = "Validates a proposed clinical plan against safety rules. MUST be called before finalizing any plan."
    args_schema: Type[BaseModel] = SafetyCheckInput

    def _run(self, plan_overview: str, risk_factors: str) -> str:
        """Uses a specialized LLM to audit the plan for risks."""
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                temperature=0.5,
                google_api_key=settings.GEMINI_API_KEY
            )

            system_prompt = """You are a Clinical Safety Reviewer.
            Your job is to audit clinical CBT plans for genuine safety concerns.
            
            BE BALANCED: Most standard CBT interventions are safe. Only flag REAL risks like:
            - Plans involving active suicidal ideation without crisis protocols
            - Exposure therapy for unstabilized trauma (PTSD without grounding skills first)
            - Techniques contraindicated for the specific condition
            - Missing safety nets for high-risk presentations
            
            If the plan follows standard CBT practice and has no major red flags, mark it as SAFE.
            Do NOT flag minor stylistic preferences or theoretical disagreements.

            Output ONLY a JSON object:
            {
                "is_safe": true/false,
                "risk_flags": ["only genuine safety risks, empty if safe"],
                "required_modifications": ["only critical changes, empty if safe"],
                "reasoning": "brief explanation"
            }
            """

            user_msg = f"""
            **Proposed Plan**: {plan_overview}
            **Patient Risk Factors**: {risk_factors}

            Review this plan. If it follows standard CBT practice with no major contraindications, approve it.
            Only flag genuine safety concerns, not theoretical preferences.
            """

            response = llm.invoke([("system", system_prompt), ("user", user_msg)])
            
            # Handle response content - Gemini returns list of parts
            # Each part can be a dict like {'type': 'text', 'text': '...'}
            content = response.content
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and 'text' in part:
                        text_parts.append(part['text'])
                    elif isinstance(part, str):
                        text_parts.append(part)
                content = " ".join(text_parts)
            content = str(content)
            
            # Clean up response to ensure valid JSON (sometimes LLMs add markdown blocks)
            content = content.replace("```json", "").replace("```", "").strip()
            return content

        except Exception as e:
            return json.dumps({
                "is_safe": False,
                "risk_flags": ["Safety check failed"],
                "required_modifications": ["Manual review required"],
                "reasoning": f"Error during safety check: {str(e)}"
            })
