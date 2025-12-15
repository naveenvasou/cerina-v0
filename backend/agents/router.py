import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.settings import settings


class RouterAgent:
    """
    Conversational Router that classifies user intent and decides workflow routing.
    
    Routes:
    - "conversation": Casual talk, greetings, help queries - responds directly
    - "planner": CBT exercise requests - routes to Planner agent
    - "draftsman": User provides a pre-made plan - routes directly to Draftsman
    """
    
    def __init__(self, model_name: str = "gemini-2.5-flash-lite"):
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.3,  # Lower temperature for consistent classification
            google_api_key=settings.GEMINI_API_KEY
        )
        self.system_prompt = """You are an intelligent routing assistant for a CBT (Cognitive Behavioral Therapy) application called Cerina.

            Analyze the user's message and classify their intent into ONE of these categories:

            1. "conversation" - Use this for:
            - Greetings (Hi, Hello, Hey)
            - Questions about the app or how it works
            - General small talk or casual conversation
            - Asking what you can do or how you can help
            - Thank you messages or feedback
            - If user just asks basic questions like "What is CBT?" or "What is Cerina?" etc. 
            - If you are not sure that the user wants to generate a exercise, route to conversation and ask if the user wants to create a excercise.

            2. "planner" - Use this for:
            - Requests for CBT exercises or therapy sessions
            - Expressing mental health concerns (anxiety, stress, depression, negative thoughts)
            - Asking for help with emotional or psychological issues
            - Wanting to work through a problem or situation

            3. "draftsman" - Use this for:
            - User provides their own detailed plan or outline and wants it formatted/drafted
            - User has a specific structure they want turned into a CBT exercise

            RESPONSE FORMAT:
            You MUST respond with valid JSON only, no markdown, no extra text:
            {{"route": "<conversation|planner|draftsman>", "response": "<your response if conversation, empty string otherwise>"}}

            If route is "conversation", provide a friendly, helpful response in the "response" field.
            If route is "planner" or "draftsman", set "response" to an empty string "".

            Examples:
            User: "Hi there!"
            {{"route": "conversation", "response": "Hello! I'm Cerina, your CBT companion. I can help you create personalized cognitive behavioral therapy exercises. What's on your mind today?"}}

            User: "I'm feeling anxious about my upcoming exam"
            {{"route": "planner", "response": ""}}

            User: "Here's my plan: Step 1 - Identify the thought, Step 2 - Challenge it. Can you draft this?"
            {{"route": "draftsman", "response": ""}}
            """

    def invoke(self, state: dict) -> dict:
        user_query = state.get('user_query', '')
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("user", "{user_query}")
        ])
        
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke({"user_query": user_query})
        
        # Parse JSON response
        try:
            # Clean response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
            
            result = json.loads(cleaned)
            route = result.get("route", "planner")
            router_response = result.get("response", "")
        except (json.JSONDecodeError, AttributeError):
            # Fallback to planner if parsing fails
            print(f"Router parsing failed, defaulting to planner. Raw: {response}")
            route = "planner"
            router_response = ""
        
        return {
            "route": route,
            "router_response": router_response
        }
