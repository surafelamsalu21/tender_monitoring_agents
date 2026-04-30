"""
Database Configuration and Session Management
Centralized database handling for the Tender Monitoring System
"""
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create database engine
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite specific configuration
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.DEBUG
    )
else:
    # PostgreSQL/MySQL configuration
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        echo=settings.DEBUG
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def _sqlite_blank_datetime_predicate(column: str) -> str:
    """Match SQLite DATETIME cells stored as empty text (breaks SQLAlchemy parsing)."""
    return f"trim(ifnull(cast({column} AS TEXT), '')) = ''"


def repair_sqlite_blank_datetime_columns() -> None:
    """
    SQLite allows '' in columns typed as DATETIME; SQLAlchemy expects NULL or valid ISO text.
    Normalize blanks so ORM loads do not raise ValueError: Invalid isoformat string: ''.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    nullable_columns: list[tuple[str, str]] = [
        ("keywords", "last_used"),
        ("tenders", "tender_date"),
        ("detailed_tenders", "deadline"),
        ("detailed_tenders", "processed_at"),
        ("monitored_pages", "last_crawled"),
        ("monitored_pages", "last_successful_crawl"),
        ("crawl_logs", "completed_at"),
    ]

    coerced_now_columns: list[tuple[str, str]] = [
        ("users", "created_at"),
        ("users", "updated_at"),
        ("keywords", "created_at"),
        ("keywords", "updated_at"),
        ("monitored_pages", "created_at"),
        ("monitored_pages", "updated_at"),
        ("tenders", "created_at"),
        ("tenders", "updated_at"),
        ("detailed_tenders", "created_at"),
        ("detailed_tenders", "updated_at"),
        ("tender_keywords", "created_at"),
        ("email_notification_settings", "created_at"),
        ("email_notification_settings", "updated_at"),
        ("email_notification_logs", "sent_at"),
        ("email_notification_logs", "created_at"),
        ("crawl_logs", "started_at"),
    ]

    with engine.begin() as conn:
        where_blank = _sqlite_blank_datetime_predicate
        for table, col in nullable_columns:
            try:
                res = conn.execute(
                    text(f"UPDATE {table} SET {col} = NULL WHERE {where_blank(col)}")
                )
                if res.rowcount:
                    logger.info(
                        "SQLite datetime repair: %s.%s set NULL (%s rows)",
                        table,
                        col,
                        res.rowcount,
                    )
            except OperationalError as e:
                logger.debug("SQLite datetime repair skipped %s.%s: %s", table, col, e)

        for table, col in coerced_now_columns:
            try:
                res = conn.execute(
                    text(
                        f"UPDATE {table} SET {col} = datetime('now') "
                        f"WHERE {where_blank(col)}"
                    )
                )
                if res.rowcount:
                    logger.info(
                        "SQLite datetime repair: %s.%s set to now (%s rows)",
                        table,
                        col,
                        res.rowcount,
                    )
            except OperationalError as e:
                logger.debug("SQLite datetime repair skipped %s.%s: %s", table, col, e)


def get_db() -> Session:
    """
    Dependency to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """Create all database tables"""
    try:
        # Ensure all model modules are imported so SQLAlchemy metadata
        # includes every table (including newly added ones like users).
        import app.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        repair_sqlite_blank_datetime_columns()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise

def drop_tables():
    """Drop all database tables (for testing/reset)"""
    try:
        Base.metadata.drop_all(bind=engine)
        logger.info("Database tables dropped successfully")
    except Exception as e:
        logger.error(f"Error dropping database tables: {e}")
        raise

# ------------------------------------------------------------------------------
# This file sets up and manages the SQLAlchemy database for the Tender Monitoring System.
# It creates a database engine, session factory, and declarative base for models.
# The get_db function provides a session dependency for FastAPI routes.
# Utility functions are included to create or drop all tables in the database.
# The database connection supports both SQLite and other SQL databases (e.g., PostgreSQL).
# Logging is used to report the status of database operations for easier debugging.
# ------------------------------------------------------------------------------
 