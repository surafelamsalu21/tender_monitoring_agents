"""
Database Configuration and Session Management
Centralized database handling for the Tender Monitoring System
"""
import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create database engine
if settings.DATABASE_URL.startswith("sqlite"):
    # File-based SQLite: do NOT use StaticPool — one shared connection breaks under concurrent
    # API requests + background LangGraph tasks (sqlite3.InterfaceError: bad parameter / API misuse).
    # Use default NullPool (new connection per session checkout) with check_same_thread=False.
    # In-memory sqlite: StaticPool is correct (single connection for :memory: lifetime).
    connect_args = {"check_same_thread": False}
    url = settings.DATABASE_URL
    is_memory = ":memory:" in url
    if is_memory:
        engine = create_engine(
            url,
            connect_args=connect_args,
            poolclass=StaticPool,
            echo=settings.SQL_ECHO,
        )
    else:
        engine = create_engine(
            url,
            connect_args=connect_args,
            echo=settings.SQL_ECHO,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

else:
    # PostgreSQL/MySQL configuration
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        echo=settings.SQL_ECHO,
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


def ensure_monitored_pages_crawl_strategy_column() -> None:
    """Add crawl_strategy for existing DBs (create_all does not ALTER legacy tables)."""
    from sqlalchemy import inspect

    try:
        inspector = inspect(engine)
        if "monitored_pages" not in inspector.get_table_names():
            return
        cols = {c["name"] for c in inspector.get_columns("monitored_pages")}
        if "crawl_strategy" in cols:
            return
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE monitored_pages ADD COLUMN crawl_strategy "
                    "VARCHAR(32) DEFAULT 'crawl4ai' NOT NULL"
                )
            )
        logger.info("DB migration: monitored_pages.crawl_strategy added")
    except OperationalError as e:
        logger.warning("crawl_strategy migration skipped: %s", e)


def ensure_monitored_pages_playwright_auth_columns() -> None:
    """Add Playwright auth columns for existing DBs."""
    from sqlalchemy import inspect

    columns_sql = [
        ("auth_login_url", "VARCHAR(1000)"),
        ("auth_username_env", "VARCHAR(128)"),
        ("auth_password_env", "VARCHAR(128)"),
        ("auth_form_selectors_json", "TEXT"),
    ]
    try:
        inspector = inspect(engine)
        if "monitored_pages" not in inspector.get_table_names():
            return
        existing = {c["name"] for c in inspector.get_columns("monitored_pages")}
        for col_name, sql_type in columns_sql:
            if col_name in existing:
                continue
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE monitored_pages ADD COLUMN {col_name} {sql_type}")
                )
            logger.info("DB migration: monitored_pages.%s added", col_name)
            existing.add(col_name)
    except OperationalError as e:
        logger.warning("playwright auth columns migration skipped: %s", e)


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
        ensure_monitored_pages_crawl_strategy_column()
        ensure_monitored_pages_playwright_auth_columns()
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
 