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
    DATABASE_URL: str = Field(
        default="sqlite:///./tender_monitoring.db", env="DATABASE_URL")

    # Database backups (SQLite only)
    BACKUP_ENABLED: bool = Field(default=True, env="BACKUP_ENABLED")
    BACKUP_DIR: str = Field(default="backups", env="BACKUP_DIR")
    BACKUP_DIR_SECONDARY: str = Field(
        default="backups_secondary", env="BACKUP_DIR_SECONDARY"
    )
    BACKUP_RETENTION: int = Field(default=30, env="BACKUP_RETENTION")
    # Run backup after extraction if today's weekday is in this list.
    # Defaults align with your crawl schedule: monday,thursday.
    BACKUP_AFTER_EXTRACTION_ENABLED: bool = Field(
        default=True, env="BACKUP_AFTER_EXTRACTION_ENABLED"
    )
    BACKUP_AFTER_EXTRACTION_WEEKDAYS: str = Field(
        default="monday,wednesday,friday", env="BACKUP_AFTER_EXTRACTION_WEEKDAYS"
    )
    # On startup, if the live SQLite DB is missing/invalid, restore latest backup first.
    # Set false only when you explicitly want a fresh empty DB.
    BACKUP_AUTO_RESTORE_ON_STARTUP: bool = Field(
        default=True, env="BACKUP_AUTO_RESTORE_ON_STARTUP"
    )

    # LLM Provider
    LLM_PROVIDER: str = Field(default="anthropic", env="LLM_PROVIDER")

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", env="OPENAI_MODEL")

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    )
    ANTHROPIC_MODEL: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("ANTHROPIC_MODEL", "CLAUDE_MODEL"),
    )

    # Ollama
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434", env="OLLAMA_BASE_URL")
    OLLAMA_MODEL: str = Field(default="qwen2.5:7b", env="OLLAMA_MODEL")
    # Passed to ChatOllama(format=...). "json" asks Ollama for JSON-shaped output (helps local models follow
    # the extraction contract). Set OLLAMA_FORMAT=none to omit and use the model default.
    OLLAMA_FORMAT: str = Field(default="json", env="OLLAMA_FORMAT")
    # httpx read timeout for Ollama API (seconds). Per-request ceiling (local fast path uses 2 shorter calls).
    OLLAMA_HTTP_TIMEOUT_SEC: float = Field(
        default=600.0, env="OLLAMA_HTTP_TIMEOUT_SEC")

    # LangGraph Agent 1 checklist mode: single huge LLM call (legacy one-shot).
    AGENT1_LLM_TIMEOUT_SEC: int = Field(
        default=300, env="AGENT1_LLM_TIMEOUT_SEC")

    # LangGraph Agent 1: ``auto`` → two-step fast path when LLM_PROVIDER=ollama; ``fast``/``legacy`` force mode.
    PIPELINE_AGENT1_MODE: str = Field(
        default="auto", env="PIPELINE_AGENT1_MODE")
    AGENT1_FAST_MAX_INPUT_CHARS: int = Field(
        default=12000, env="AGENT1_FAST_MAX_INPUT_CHARS")
    AGENT1_FAST_STEP_TIMEOUT_SEC: int = Field(
        default=300, env="AGENT1_FAST_STEP_TIMEOUT_SEC")
    AGENT1_FAST_SCREEN_BATCH: int = Field(
        default=5, env="AGENT1_FAST_SCREEN_BATCH")

    # Screening precision. Mission alignment, geography and firm eligibility are
    # mandatory, which three broad criteria alone satisfy — so a vaguely-worded
    # "development consultancy in Ethiopia" used to pass. Requiring one of
    # sector_relevance/activity_fit closes that, at the cost of raising the
    # effective bar from 3-of-5 to 4-of-5. Set false to fall back to the plain
    # 3-of-5 rule if genuine opportunities start disappearing.
    SCREENING_REQUIRE_SECTOR_OR_ACTIVITY: bool = Field(
        default=True, env="SCREENING_REQUIRE_SECTOR_OR_ACTIVITY")

    # Agent 2 (detail enrichment). Detail pages can be very large (long PDFs,
    # bid packs), so the prompt is capped before it reaches the provider.
    AGENT2_MAX_INPUT_CHARS: int = Field(
        default=120_000, env="AGENT2_MAX_INPUT_CHARS")
    AGENT2_LLM_TIMEOUT_SEC: int = Field(
        default=240, env="AGENT2_LLM_TIMEOUT_SEC")
    # Attempts per tender for transient provider failures (429/overloaded/5xx/timeout).
    AGENT2_LLM_MAX_ATTEMPTS: int = Field(
        default=3, env="AGENT2_LLM_MAX_ATTEMPTS")
    # Raw page text kept on the detail row. Full pages are only needed for
    # spot-checking extractions, so the default is far below the old 400k.
    AGENT2_FULL_CONTENT_MAX_CHARS: int = Field(
        default=60_000, env="AGENT2_FULL_CONTENT_MAX_CHARS")
    # Keep a tender using its listing data when the detail page is unreachable
    # (anti-bot stubs, client-side-rendered notices). Set false to require a
    # successful detail extraction before a tender is reported.
    AGENT2_LISTING_FALLBACK_ENABLED: bool = Field(
        default=True, env="AGENT2_LISTING_FALLBACK_ENABLED")

    # Provider-level HTTP timeout and retry budget for hosted LLM APIs.
    LLM_REQUEST_TIMEOUT_SEC: float = Field(
        default=120.0, env="LLM_REQUEST_TIMEOUT_SEC")
    LLM_MAX_RETRIES: int = Field(default=3, env="LLM_MAX_RETRIES")

    # Email Configuration
    SMTP_HOST: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USE_TLS: bool = Field(default=True, env="SMTP_USE_TLS")
    EMAIL_USER: str = Field(..., env="EMAIL_USER")
    EMAIL_PASSWORD: str = Field(..., env="EMAIL_PASSWORD")
    # Retry failed recipient sends from transient network/SMTP errors.
    EMAIL_RETRY_ENABLED: bool = Field(default=True, env="EMAIL_RETRY_ENABLED")
    EMAIL_RETRY_INTERVAL_MINUTES: int = Field(
        default=30, env="EMAIL_RETRY_INTERVAL_MINUTES"
    )
    EMAIL_RETRY_MAX_ATTEMPTS: int = Field(default=48, env="EMAIL_RETRY_MAX_ATTEMPTS")

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
    SKIP_EXPIRED_AFTER_AGENT1: bool = Field(
        default=True, env="SKIP_EXPIRED_AFTER_AGENT1")

    # Notifications: never email an opportunity whose deadline has passed. The
    # earlier gates run at extraction time, but a tender saved with a valid
    # deadline expires while it sits in the backlog, so the send path needs its
    # own check against today's date.
    NOTIFY_SKIP_EXPIRED: bool = Field(
        default=True, env="NOTIFY_SKIP_EXPIRED")
    # Rows with no deadline anywhere are dropped once their only known date is
    # this old. Mirrors Agent 2's ``max_days_old`` so behaviour is consistent.
    NOTIFY_MAX_STALE_DAYS: int = Field(
        default=90, env="NOTIFY_MAX_STALE_DAYS")

    # Pipeline: ``simple`` = crawler artifact → list structure → linear DB/agent steps; ``langgraph`` = legacy LangGraph + checklist Agent 1.
    PIPELINE_MODE: str = Field(default="simple", env="PIPELINE_MODE")
    AGENT1_STRUCTURE_LLM_TIMEOUT_SEC: int = Field(
        default=300, env="AGENT1_STRUCTURE_LLM_TIMEOUT_SEC")
    # Print Crawl4AI-style progress lines to the terminal (stderr/stdout) during simple pipeline runs.
    PIPELINE_TTY_PROGRESS: bool = Field(
        default=True, env="PIPELINE_TTY_PROGRESS")

    # Crawling Configuration
    # Weekday schedule: automatic full extraction on listed days only (skips weekends when unset).
    # Example: monday,wednesday,friday → 3 runs per week, no weekends.
    CRAWL_SCHEDULE_WEEKDAYS: str = Field(
        default="monday,wednesday,friday", env="CRAWL_SCHEDULE_WEEKDAYS"
    )
    CRAWL_SCHEDULE_TIME: str = Field(default="09:00", env="CRAWL_SCHEDULE_TIME")
    CRAWL_SCHEDULE_TIMEZONE: str = Field(
        default="Africa/Addis_Ababa", env="CRAWL_SCHEDULE_TIMEZONE"
    )
    # Fallback when CRAWL_SCHEDULE_WEEKDAYS is empty: fixed interval in hours.
    CRAWL_INTERVAL_HOURS: int = Field(default=72, env="CRAWL_INTERVAL_HOURS")
    MAX_CONCURRENT_CRAWLS: int = Field(default=5, env="MAX_CONCURRENT_CRAWLS")
    REQUEST_TIMEOUT: int = Field(default=30, env="REQUEST_TIMEOUT")

    # Scale controls for an extraction cycle. With dozens of monitored pages the
    # cycle used to be fully sequential with no bound on any single page, so one
    # slow portal could hold up every page behind it.
    #
    # Concurrency is safe at page level because tender identity (fingerprint and
    # URL lookup) is scoped to page_id, so two pages can never race on the same
    # row. Keep this modest: every page in flight is making LLM calls, and the
    # provider rate limit is the real ceiling.
    MAX_CONCURRENT_PAGES: int = Field(default=3, env="MAX_CONCURRENT_PAGES")
    # Hard ceiling for one page (harvest + Agent 1 + Agent 2 + Agent 3). Generous
    # enough for a page with many tenders, but bounded so a hung page cannot stall
    # the cycle indefinitely.
    PAGE_PROCESSING_TIMEOUT_SEC: int = Field(
        default=1800, env="PAGE_PROCESSING_TIMEOUT_SEC")
    # Scheduled runs honour each page's crawl_frequency_hours by default, so pages
    # can be staggered. Set true to restore the old behaviour of crawling every
    # active page on every scheduled tick.
    SCHEDULED_CRAWL_FORCE_ALL_PAGES: bool = Field(
        default=False, env="SCHEDULED_CRAWL_FORCE_ALL_PAGES")

    # Playwright (authenticated / JS-heavy sources) — credentials stay in .env, referenced by name
    PLAYWRIGHT_HEADLESS: bool = Field(default=True, env="PLAYWRIGHT_HEADLESS")
    PLAYWRIGHT_SLOW_MO_MS: int = Field(default=0, env="PLAYWRIGHT_SLOW_MO_MS")
    PLAYWRIGHT_TIMEOUT_MS: int = Field(
        default=90000, env="PLAYWRIGHT_TIMEOUT_MS")
    PLAYWRIGHT_MAX_PAGES: int = Field(default=4, env="PLAYWRIGHT_MAX_PAGES")
    # networkidle can hang on some portals; load is usually safer
    PLAYWRIGHT_GOTO_WAIT: str = Field(
        default="load", env="PLAYWRIGHT_GOTO_WAIT")
    PLAYWRIGHT_AUTH_LOGIN_URL: Optional[str] = Field(
        default=None, env="PLAYWRIGHT_AUTH_LOGIN_URL")
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
    GEMINI_MODEL: str = Field(default="gemini-1.5-flash", env="GEMINI_MODEL")
    GROQ_API_KEY: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    GROQ_MODEL: str = Field(
        default="llama-3.3-70b-versatile", env="GROQ_MODEL")

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
    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production", env="SECRET_KEY")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=480, env="ACCESS_TOKEN_EXPIRE_MINUTES")

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
