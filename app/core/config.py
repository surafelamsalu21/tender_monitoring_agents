"""
Application Configuration
Centralized configuration management for the Tender Monitoring System
"""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "Tender Monitoring System"
    VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./tender_monitoring.db", env="DATABASE_URL")
    
    # LLM Provider
    LLM_PROVIDER: str = Field(default="openai", env="LLM_PROVIDER")

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", env="OPENAI_MODEL")

    # Ollama
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_MODEL: str = Field(default="qwen2.5:3b", env="OLLAMA_MODEL")
    
    # Email Configuration
    SMTP_HOST: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USE_TLS: bool = Field(default=True, env="SMTP_USE_TLS")
    EMAIL_USER: str = Field(..., env="EMAIL_USER")
    EMAIL_PASSWORD: str = Field(..., env="EMAIL_PASSWORD")
    
    # Team Emails
    ESG_TEAM_EMAIL: str = Field(..., env="ESG_TEAM_EMAIL")
    CREDIT_RATING_TEAM_EMAIL: str = Field(..., env="CREDIT_RATING_TEAM_EMAIL")
    
    # Crawling Configuration
    CRAWL_INTERVAL_HOURS: int = Field(default=3, env="CRAWL_INTERVAL_HOURS")
    MAX_CONCURRENT_CRAWLS: int = Field(default=5, env="MAX_CONCURRENT_CRAWLS")
    REQUEST_TIMEOUT: int = Field(default=30, env="REQUEST_TIMEOUT")
    
    # AI Models
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(default=["*"], env="ALLOWED_ORIGINS")
    
    # Security
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# ------------------------------------------------------------------------------
# This file defines app-wide configuration using Pydantic settings.
# It loads settings from environment variables and .env file for deployment.
# Centralizes all config: database, LLM, SMTP/email, crawling, logging, security.
# The Settings class provides strongly typed access to all environment config.
# Used anywhere in the Tender Monitoring System by importing `settings`.
# Updates to .env or env variables immediately affect configuration here.
# ------------------------------------------------------------------------------