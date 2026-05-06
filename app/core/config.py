"""
Application Configuration
Centralized configuration management for the Tender Monitoring System
"""
from pathlib import Path
from typing import List, Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )
    
    # Application
    APP_NAME: str = "Precise Tender Monitoring"
    VERSION: str = "2.0.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    # Log every SQL statement (noisy). Off by default even when DEBUG=true so uvicorn --reload stays readable.
    SQL_ECHO: bool = Field(default=False, env="SQL_ECHO")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8000, env="PORT")
    
    # Database
    DATABASE_URL: str = Field(default="sqlite:///./tender_monitoring.db", env="DATABASE_URL")

    # Database backups (SQLite only)
    BACKUP_ENABLED: bool = Field(default=True, env="BACKUP_ENABLED")
    BACKUP_DIR: str = Field(default="backups", env="BACKUP_DIR")
    BACKUP_INTERVAL_HOURS: int = Field(default=24, env="BACKUP_INTERVAL_HOURS")
    BACKUP_RETENTION: int = Field(default=30, env="BACKUP_RETENTION")
    # Delay before the first backup runs after startup (avoids contention with init).
    BACKUP_INITIAL_DELAY_SECONDS: int = Field(default=300, env="BACKUP_INITIAL_DELAY_SECONDS")
    
    # LLM Provider
    LLM_PROVIDER: str = Field(default="openai", env="LLM_PROVIDER")

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-5.5", env="OPENAI_MODEL")

    # Ollama
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_MODEL: str = Field(default="qwen2.5:7b", env="OLLAMA_MODEL")
    # Passed to ChatOllama(format=...). "json" asks Ollama for JSON-shaped output (helps local models follow
    # the extraction contract). Set OLLAMA_FORMAT=none to omit and use the model default.
    OLLAMA_FORMAT: str = Field(default="json", env="OLLAMA_FORMAT")
    # httpx read timeout for Ollama API (seconds). Per-request ceiling (local fast path uses 2 shorter calls).
    OLLAMA_HTTP_TIMEOUT_SEC: float = Field(default=600.0, env="OLLAMA_HTTP_TIMEOUT_SEC")

    # LangGraph Agent 1 checklist mode: single huge LLM call (legacy one-shot).
    AGENT1_LLM_TIMEOUT_SEC: int = Field(default=300, env="AGENT1_LLM_TIMEOUT_SEC")

    # LangGraph Agent 1: ``auto`` → two-step fast path when LLM_PROVIDER=ollama; ``fast``/``legacy`` force mode.
    PIPELINE_AGENT1_MODE: str = Field(default="auto", env="PIPELINE_AGENT1_MODE")
    AGENT1_FAST_MAX_INPUT_CHARS: int = Field(default=12000, env="AGENT1_FAST_MAX_INPUT_CHARS")
    AGENT1_FAST_STEP_TIMEOUT_SEC: int = Field(default=300, env="AGENT1_FAST_STEP_TIMEOUT_SEC")
    AGENT1_FAST_SCREEN_BATCH: int = Field(default=5, env="AGENT1_FAST_SCREEN_BATCH")
    
    # Email Configuration
    SMTP_HOST: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USE_TLS: bool = Field(default=True, env="SMTP_USE_TLS")
    EMAIL_USER: str = Field(..., env="EMAIL_USER")
    EMAIL_PASSWORD: str = Field(..., env="EMAIL_PASSWORD")
    
    # Default recipient for dev-only tests (e.g. Agent 3 smoke test). Optional.
    # Legacy env names still accepted: ESG_TEAM_EMAIL, CREDIT_RATING_TEAM_EMAIL.
    SCREENING_DEFAULT_TEST_EMAIL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "SCREENING_DEFAULT_TEST_EMAIL",
            "ESG_TEAM_EMAIL",
            "CREDIT_RATING_TEAM_EMAIL",
        ),
    )
    
    # Listing / Agent 1: drop tenders when closing date from listing row or Agent-1 step3.deadline is before today (UTC date).
    SKIP_EXPIRED_AFTER_AGENT1: bool = Field(default=True, env="SKIP_EXPIRED_AFTER_AGENT1")

    # Pipeline: ``simple`` = crawler artifact → list structure → linear DB/agent steps; ``langgraph`` = legacy LangGraph + checklist Agent 1.
    PIPELINE_MODE: str = Field(default="simple", env="PIPELINE_MODE")
    AGENT1_STRUCTURE_LLM_TIMEOUT_SEC: int = Field(default=300, env="AGENT1_STRUCTURE_LLM_TIMEOUT_SEC")
    # Print Crawl4AI-style progress lines to the terminal (stderr/stdout) during simple pipeline runs.
    PIPELINE_TTY_PROGRESS: bool = Field(default=True, env="PIPELINE_TTY_PROGRESS")

    # Crawling Configuration
    # Fixed cadence: scheduled extraction runs every CRAWL_INTERVAL_HOURS hours.
    CRAWL_INTERVAL_HOURS: int = Field(default=12, env="CRAWL_INTERVAL_HOURS")
    MAX_CONCURRENT_CRAWLS: int = Field(default=5, env="MAX_CONCURRENT_CRAWLS")
    REQUEST_TIMEOUT: int = Field(default=30, env="REQUEST_TIMEOUT")

    # Playwright (authenticated / JS-heavy sources) — credentials stay in .env, referenced by name
    PLAYWRIGHT_HEADLESS: bool = Field(default=True, env="PLAYWRIGHT_HEADLESS")
    PLAYWRIGHT_SLOW_MO_MS: int = Field(default=0, env="PLAYWRIGHT_SLOW_MO_MS")
    PLAYWRIGHT_TIMEOUT_MS: int = Field(default=90000, env="PLAYWRIGHT_TIMEOUT_MS")
    PLAYWRIGHT_MAX_PAGES: int = Field(default=4, env="PLAYWRIGHT_MAX_PAGES")
    # networkidle can hang on some portals; load is usually safer
    PLAYWRIGHT_GOTO_WAIT: str = Field(default="load", env="PLAYWRIGHT_GOTO_WAIT")
    PLAYWRIGHT_AUTH_LOGIN_URL: Optional[str] = Field(default=None, env="PLAYWRIGHT_AUTH_LOGIN_URL")
    PLAYWRIGHT_AUTH_USERNAME_ENV: str = Field(
        default="CRAWL_AUTH_USERNAME", env="PLAYWRIGHT_AUTH_USERNAME_ENV"
    )
    PLAYWRIGHT_AUTH_PASSWORD_ENV: str = Field(
        default="CRAWL_AUTH_PASSWORD", env="PLAYWRIGHT_AUTH_PASSWORD_ENV"
    )
    PLAYWRIGHT_AUTH_USER_SELECTOR: str = Field(
        default='input[name="username"], input[name="email"], input[name="user"], '
        'input[type="email"]',
        env="PLAYWRIGHT_AUTH_USER_SELECTOR",
    )
    PLAYWRIGHT_AUTH_PASSWORD_SELECTOR: str = Field(
        default='input[name="password"], input[type="password"]',
        env="PLAYWRIGHT_AUTH_PASSWORD_SELECTOR",
    )
    PLAYWRIGHT_AUTH_SUBMIT_SELECTOR: str = Field(
        default='button[type="submit"], input[type="submit"]',
        env="PLAYWRIGHT_AUTH_SUBMIT_SELECTOR",
    )
    
    # AI Models
    GEMINI_API_KEY: Optional[str] = Field(default=None, env="GEMINI_API_KEY")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: Optional[str] = Field(default=None, env="LOG_FILE")
    
    # CORS
    ALLOWED_ORIGINS: List[str] = Field(default=["*"], env="ALLOWED_ORIGINS")

    # Authentication / Access Control
    ALLOWED_COMPANY_EMAIL_DOMAINS: str = Field(
        default="preciseethiopia.com",
        env="ALLOWED_COMPANY_EMAIL_DOMAINS"
    )
    DEFAULT_ADMIN_EMAIL: str = Field(
        default="admin@preciseethiopia.com",
        env="DEFAULT_ADMIN_EMAIL"
    )
    DEFAULT_ADMIN_PASSWORD: str = Field(
        default="ChangeMe123!",
        env="DEFAULT_ADMIN_PASSWORD"
    )
    
    # Security
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    @model_validator(mode="after")
    def resolve_sqlite_relative_to_project(self) -> "Settings":
        """
        Anchor relative sqlite paths to the project root (parent of `app/`), not process cwd.
        Avoids loading a different/outdated DB when uvicorn is started from another directory.
        """
        url = self.DATABASE_URL
        if not url.startswith("sqlite"):
            return self
        try:
            parsed = make_url(url)
        except Exception:
            return self
        db = parsed.database
        if not db or db == ":memory:":
            return self
        db_path = Path(db)
        if db_path.is_absolute():
            return self
        project_root = Path(__file__).resolve().parents[2]
        abs_db = (project_root / db_path).resolve()
        self.DATABASE_URL = str(parsed.set(database=str(abs_db)))
        return self

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