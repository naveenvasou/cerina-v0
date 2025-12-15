"""
Application Settings

This module provides a centralized settings class that loads environment 
variables from the .env file and makes them available throughout the application.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load the .env file from the project root
# The project root is one level up from the backend folder
PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    """
    Centralized settings class that provides access to all environment variables.
    Usage:
        from backend.settings import settings
        api_key = settings.GEMINI_API_KEY
    """
    
    # Google Gemini API Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Tavily API Key (for clinical protocol search)
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Debug mode
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    
    @classmethod
    def validate(cls) -> None:
        """Validate that all required environment variables are set."""
        errors = []
        
        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is not set in .env file")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")


# Create a singleton instance for easy import
settings = Settings()
