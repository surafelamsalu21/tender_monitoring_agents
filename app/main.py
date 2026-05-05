"""
FastAPI Main Application
Entry point for the Tender Monitoring System API
"""
from datetime import datetime, timezone
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import create_tables
from app.core.init_data import ensure_default_screening_keywords
from app.services.scheduler import TenderScheduler
from app.api.main import api_router

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global scheduler
    
    logger.info(f"Starting {settings.APP_NAME}...")

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
    allow_credentials=True,
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


@app.post("/trigger-extraction")
async def trigger_manual_extraction(force: bool = Query(True)):
    """Manually trigger tender extraction. Use force=false to respect crawl_frequency_hours."""
    if not scheduler:
        return {"error": "Scheduler not initialized"}
    
    try:
        asyncio.create_task(scheduler.run_extraction_once(force=force))
        mode = (settings.PIPELINE_MODE or "simple").strip().lower()
        return {
            "message": "Manual extraction triggered successfully",
            "force": force,
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
