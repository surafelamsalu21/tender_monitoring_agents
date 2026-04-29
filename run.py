"""
FastAPI Application Runner
Main entry point for the Tender Monitoring System FastAPI backend
"""

import os
import sys

# Fix Windows console encoding for Unicode support
if os.name == 'nt':  # Windows
    import locale
    import codecs
    
    # Set console to UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    else:
        # Fallback for older Python versions
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Then your existing imports and code...
from app.core.logging import setup_logging

import uvicorn
import asyncio
import logging
from pathlib import Path

# Add the project root to Python path
import sys
sys.path.append(str(Path(__file__).parent))

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import create_tables
from app.core.init_data import initialize_default_data
from app.main import app

def initialize_application():
    """Initialize the application with logging and database"""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Initializing Tender Monitoring System...")
    
    # Create database tables
    try:
        create_tables()
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Initialize default data
    try:
        initialize_default_data()
        logger.info("Default data initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize default data: {e}")
        raise
    
    logger.info("Application initialization completed")

def main():
    """Main entry point"""
    try:
        # Initialize the application
        initialize_application()
        
        # Run the FastAPI server
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=8000,
            reload=settings.DEBUG,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        raise

if __name__ == "__main__":
    main()
