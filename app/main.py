"""
FastAPI Main Application
Entry point for the Tender Monitoring System API
"""
from datetime import datetime, timezone
import asyncio

from app.core.asyncio_windows import apply as _apply_windows_asyncio_policy

_apply_windows_asyncio_policy()
import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.services.crawl_schedule import schedule_description, uses_weekday_schedule
from app.core.database import create_tables
from app.core.init_data import ensure_default_screening_keywords
from app.services.db_backup import auto_restore_live_db_from_latest_backup_if_needed
from app.services.scheduler import TenderScheduler
from app.api.main import api_router
from app.auth.deps import require_analyst_or_above
from app.models.user import User

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global scheduler
    
    logger.info(f"Starting {settings.APP_NAME}...")

    # Safety: if DB is missing/corrupted, restore latest backup before schema init.
    restore_result = auto_restore_live_db_from_latest_backup_if_needed()
    if restore_result.get("restored"):
        logger.warning(
            "Database auto-restored on startup from backup: %s",
            restore_result.get("from_backup"),
        )

    # Always ensure DB schema exists, even when app is started directly
    # via `uvicorn app.main:app`.
    create_tables()
    ensure_default_screening_keywords()

    # Initialize scheduler
    scheduler = TenderScheduler()
    
    # Start background tasks
    await scheduler.start()
    logger.info("Background scheduler started")
    
    yield
    
    # Cleanup
    logger.info(f"Shutting down {settings.APP_NAME}...")
    if scheduler:
        await scheduler.stop()
    logger.info("Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered tender screening and notifications (Precise).",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    # False so `allow_origins=["*"]` works in browsers (credentials + * is invalid per CORS).
    # Auth uses Bearer tokens in headers, not cookies.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"{settings.APP_NAME} API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scheduler_running": scheduler.running if scheduler else False
    }

@app.get("/extraction-status")
async def get_extraction_status():
    """Return whether a tender extraction job is currently running."""
    if not scheduler:
        return {"running": False, "started_at": None}
    return {
        "running": getattr(scheduler, "extraction_in_progress", False),
        "started_at": getattr(scheduler, "extraction_started_at", None),
    }


@app.get("/scheduler-status")
async def get_scheduler_status():
    """Return cadence + last/next run timestamps so the Settings UI can display real status."""
    schedule_label = schedule_description()
    base = {
        "interval_hours": settings.CRAWL_INTERVAL_HOURS,
        "schedule_description": schedule_label,
        "uses_weekday_schedule": uses_weekday_schedule(),
        "schedule_weekdays": settings.CRAWL_SCHEDULE_WEEKDAYS,
        "schedule_time": settings.CRAWL_SCHEDULE_TIME,
        "schedule_timezone": settings.CRAWL_SCHEDULE_TIMEZONE,
    }
    if not scheduler:
        return {
            "active": False,
            "in_progress": False,
            "started_at": None,
            "last_run_at": None,
            "next_run_at": None,
            **base,
        }
    return {
        "active": bool(getattr(scheduler, "running", False)),
        "in_progress": getattr(scheduler, "extraction_in_progress", False),
        "started_at": getattr(scheduler, "extraction_started_at", None),
        "last_run_at": getattr(scheduler, "last_extraction_at", None),
        "next_run_at": getattr(scheduler, "next_extraction_at", None),
        **base,
    }


@app.post("/trigger-extraction")
async def trigger_manual_extraction(
    force: bool = Query(True),
    _: User = Depends(require_analyst_or_above),
):
    """Manually trigger tender extraction. Use force=false to respect crawl_frequency_hours."""
    if not scheduler:
        return {"error": "Scheduler not initialized"}

    # A cycle over many pages runs for a long time, so tell the caller instead of
    # silently launching a second one that competes for the same tables.
    if getattr(scheduler, "extraction_in_progress", False):
        return {
            "message": "Extraction already in progress",
            "started_at": getattr(scheduler, "extraction_started_at", None),
            "triggered": False,
        }

    try:
        asyncio.create_task(scheduler.run_extraction_once(force=force))
        mode = (settings.PIPELINE_MODE or "simple").strip().lower()
        return {
            "message": "Manual extraction triggered successfully",
            "force": force,
            "triggered": True,
            "pipeline_mode": mode,
            "hint": "simple = harvest artifact → list structure → Agent 2/3; langgraph = legacy checklist Agent 1",
        }
    except Exception as e:
        logger.error(f"Error triggering manual extraction: {e}")
        return {"error": str(e)}

# Mount static files for frontend
#app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
