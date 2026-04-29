import logging
import logging.handlers
import sys
import os
from pathlib import Path
from app.core.config import settings

def setup_logging():
    """Setup application logging with Windows Unicode support"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create formatter without emojis for Windows compatibility
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler with UTF-8 encoding for Windows
    if os.name == 'nt':  # Windows
        # Force UTF-8 encoding on Windows
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if specified) with UTF-8 encoding
    if settings.LOG_FILE:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'  # Explicit UTF-8 encoding
        )
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Default file handler with UTF-8 encoding
    default_file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "tender_monitoring.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'  # Explicit UTF-8 encoding
    )
    default_file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    default_file_handler.setFormatter(formatter)
    root_logger.addHandler(default_file_handler)
    
    # Set specific logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    logging.info("Logging configured successfully")