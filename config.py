import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    DATABASE_URL = "sqlite:///./tender_agent.db"
    
    # OpenAI API (for LangGraph agents)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Email Configuration
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    EMAIL_USER = os.getenv("EMAIL_USER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    
    # Scheduler
    CRAWL_INTERVAL_MINUTES = 10  # Changed to minutes for testing
    
    # Teams
    ESG_TEAM_EMAIL = os.getenv("ESG_TEAM_EMAIL")
    CREDIT_RATING_TEAM_EMAIL = os.getenv("CREDIT_RATING_TEAM_EMAIL")
    
    # Default Keywords
    ESG_KEYWORDS = [
        "environmental", "sustainability", "green", "carbon", "climate", 
        "renewable", "esg","ESG", "social responsibility", "governance", 
        "sustainable development", "environmental impact"
    ]
    
    CREDIT_RATING_KEYWORDS = [
        "credit rating", "financial assessment", "risk evaluation", 
        "credit analysis", "rating agency", "financial review", 
        "creditworthiness", "financial audit", "risk assessment"
    ]
