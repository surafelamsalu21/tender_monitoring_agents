"""
FastAPI Main Application
Entry point for the Tender Monitoring System API
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import create_tables
from app.services.scheduler import TenderScheduler
from app.api.main import api_router

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global scheduler
    
    logger.info("Starting Tender Monitoring System...")
    
    # Initialize scheduler
    scheduler = TenderScheduler()
    
    # Start background tasks
    await scheduler.start()
    logger.info("Background scheduler started")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Tender Monitoring System...")
    if scheduler:
        await scheduler.stop()
    logger.info("Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Tender Monitoring System",
    description="AI-powered tender monitoring and notification system",
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
        "message": "Tender Monitoring System API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z",
        "scheduler_running": scheduler.running if scheduler else False
    }

@app.post("/trigger-extraction")
async def trigger_manual_extraction():
    """Manually trigger tender extraction"""
    if not scheduler:
        return {"error": "Scheduler not initialized"}
    
    try:
        # Run extraction in background
        asyncio.create_task(scheduler.run_extraction_once())
        return {"message": "Manual extraction triggered successfully"}
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
