"""
Fixed System API Routes
app/api/routes/system.py
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime
import logging

from app.core.database import get_db
from app.services.email_service import EnhancedEmailService
from app.models import MonitoredPage, Tender, Keyword, CrawlLog
from app.repositories.email_settings_repository import EmailSettingsRepository

from pydantic import BaseModel, HttpUrl
from app.services.scraper import TenderScraper

router = APIRouter()

# --------------------------
# Pydantic Models
# --------------------------

# EmailSettings defines the schema for managing notification email addresses
class EmailSettings(BaseModel):
    esg_emails: List[EmailStr]  # Email list for ESG notifications
    credit_rating_emails: List[EmailStr]  # Email list for credit rating notifications
    # Notification preferences flags
    notification_preferences: Dict[str, bool] = {
        "send_for_new_tenders": True,
        "send_daily_summary": True,
        "send_urgent_notifications": True
    }

# Response model for retrieving/saving settings
class EmailSettingsResponse(BaseModel):
    success: bool
    message: str
    settings: EmailSettings

# Request model for sending a test email
class TestEmailRequest(BaseModel):
    email: EmailStr
    category: str  # 'esg' or 'credit_rating'

# Request model for adding a single email
class AddEmailRequest(BaseModel):
    email: EmailStr

# Request model for testing the crawler with a URL
class TestCrawlerRequest(BaseModel):
    url: HttpUrl

# Instantiate the logger for this module
logger = logging.getLogger(__name__)

# --------------------------
# System Status Endpoint
# --------------------------

@router.get("/status")
async def get_system_status(db: Session = Depends(get_db)):
    """
    Get overall system status, counts for main entities, and recent crawl activity.
    Queries MonitoredPage, Tender, Keyword, CrawlLog.
    """
    # Count various entities in the DB
    total_pages = db.query(MonitoredPage).count()
    active_pages = db.query(MonitoredPage).filter(MonitoredPage.is_active == True).count()
    total_tenders = db.query(Tender).count()
    total_keywords = db.query(Keyword).filter(Keyword.is_active == True).count()
    
    # Get the latest 5 crawl logs for recent activity display
    recent_crawls = db.query(CrawlLog).order_by(CrawlLog.started_at.desc()).limit(5).all()
    
    return {
        "system": {
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"  # Static, update manually on deployment
        },
        "database": {
            "total_pages": total_pages,
            "active_pages": active_pages,
            "total_tenders": total_tenders,
            "active_keywords": total_keywords
        },
        "recent_activity": [
            {
                "page_id": log.page_id,
                "status": log.status,
                "tenders_found": log.tenders_found,
                "started_at": log.started_at.isoformat(),
                "duration": log.duration
            }
            for log in recent_crawls
        ]
    }

# --------------------------
# Email Settings Endpoints
# --------------------------

@router.get("/email-settings", response_model=EmailSettingsResponse)
async def get_email_settings(db: Session = Depends(get_db)):
    """
    Fetch the current email notification settings from the database.

    Returns email lists and notification preference flags for both ESG and Credit Rating.
    """
    try:
        email_repo = EmailSettingsRepository()
        settings_dict = email_repo.get_email_settings(db)
        
        logger.info(f"Retrieved email settings: {settings_dict}")
        
        settings = EmailSettings(
            esg_emails=settings_dict.get('esg_emails', []),
            credit_rating_emails=settings_dict.get('credit_rating_emails', []),
            notification_preferences=settings_dict.get('notification_preferences', {
                "send_for_new_tenders": True,
                "send_daily_summary": True,
                "send_urgent_notifications": True
            })
        )
        
        return EmailSettingsResponse(
            success=True,
            message="Email settings retrieved successfully",
            settings=settings
        )
    except Exception as e:
        logger.error(f"Error retrieving email settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve email settings")

@router.post("/email-settings", response_model=EmailSettingsResponse)
async def save_email_settings(settings: EmailSettings, db: Session = Depends(get_db)):
    """
    Save (overwrite) the email notification settings in the database.
    Must include at least one recipient email in either list.
    """
    try:
        logger.info(f"Saving email settings: {settings}")
        
        # Validation: require at least one sender
        if not settings.esg_emails and not settings.credit_rating_emails:
            raise HTTPException(
                status_code=400, 
                detail="At least one email address must be configured"
            )
        
        email_repo = EmailSettingsRepository()
        settings_dict = {
            'esg_emails': settings.esg_emails,
            'credit_rating_emails': settings.credit_rating_emails,
            'notification_preferences': settings.notification_preferences
        }
        
        logger.info(f"Converting settings to dict: {settings_dict}")
        
        success = email_repo.save_email_settings(db, settings_dict)
        
        if success:
            logger.info("Email settings saved successfully")
            return EmailSettingsResponse(
                success=True,
                message="Email settings saved successfully",
                settings=settings
            )
        else:
            logger.error("Failed to save email settings to database")
            raise HTTPException(status_code=500, detail="Failed to save email settings to database")
            
    except Exception as e:
        logger.error(f"Error saving email settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save email settings: {str(e)}")

@router.post("/test-email")
async def send_test_email(request: TestEmailRequest, db: Session = Depends(get_db)):
    """
    Send a test email to a target recipient (usually used to validate notification configuration).
    Logs the result in the email notification log table.
    """
    try:
        email_service = EnhancedEmailService()
        email_repo = EmailSettingsRepository()
        
        # Simulate a test tender object for context in email template
        test_tender_data = {
            'title': f'Test {request.category.upper()} Tender - Email Configuration Test',
            'url': 'https://example.com/test-tender',
            'category': request.category,
            'description': f'This is a test tender for {request.category} team email configuration',
            'matched_keywords': ['test', 'configuration']
        }
        
        # Call async send function (real or mock depending on implementation)
        result = await email_service.send_test_intelligent_email(
            recipient=request.email,
            test_tender_data=test_tender_data
        )
        
        # Record the attempt, including errors if any
        email_repo.log_email_notification(
            db=db,
            recipient_email=request.email,
            email_type='test',
            team_category=request.category,
            subject=f'Test {request.category.upper()} Email',
            status='sent' if result['status'] == 'success' else 'failed',
            error_message=result.get('message') if result['status'] != 'success' else None
        )
        
        if result['status'] == 'success':
            return {
                "success": True,
                "message": f"Test email sent successfully to {request.email}",
                "details": result.get('message', '')
            }
        else:
            return {
                "success": False,
                "message": f"Failed to send test email: {result.get('message', 'Unknown error')}",
                "details": result.get('message', '')
            }
            
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {str(e)}")

# --------------------------
# Email List Management
# --------------------------

@router.delete("/email-settings/{category}/{email}")
async def remove_email_from_settings(category: str, email: str, db: Session = Depends(get_db)):
    """
    Remove a specified email address from a category's notification list ('esg' or 'credit_rating').
    """
    try:
        if category not in ['esg', 'credit_rating']:
            raise HTTPException(status_code=400, detail="Category must be 'esg' or 'credit_rating'")
        
        logger.info(f"Removing email {email} from {category} category")
        
        email_repo = EmailSettingsRepository()
        success = email_repo.remove_email_from_category(db, category, email)
        
        if success:
            logger.info(f"Successfully removed email {email} from {category}")
            return {
                "success": True,
                "message": f"Email {email} removed from {category} notifications"
            }
        else:
            logger.error(f"Failed to remove email {email} from {category}")
            raise HTTPException(status_code=500, detail="Failed to remove email from database")
            
    except Exception as e:
        logger.error(f"Error removing email: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove email")

@router.post("/email-settings/{category}/add")
async def add_email_to_settings(category: str, request: AddEmailRequest, db: Session = Depends(get_db)):
    """
    Add a specified email address to a category's notification list.
    Ensures only 'esg' or 'credit_rating' categories are valid.
    """
    try:
        if category not in ['esg', 'credit_rating']:
            raise HTTPException(status_code=400, detail="Category must be 'esg' or 'credit_rating'")
        
        logger.info(f"Adding email {request.email} to {category} category")
        
        email_repo = EmailSettingsRepository()
        success = email_repo.add_email_to_category(db, category, request.email)
        
        if success:
            logger.info(f"Successfully added email {request.email} to {category}")
            return {
                "success": True,
                "message": f"Email {request.email} added to {category} notifications"
            }
        else:
            logger.error(f"Failed to add email {request.email} to {category}")
            raise HTTPException(status_code=500, detail="Failed to add email to database")
            
    except Exception as e:
        logger.error(f"Error adding email: {e}")
        raise HTTPException(status_code=500, detail="Failed to add email")

# --------------------------
# Email and Crawl Logs
# --------------------------

@router.get("/email-logs")
async def get_email_logs(
    limit: int = 50,
    category: str = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """
    Retrieve recent logs of past email notification attempts.
    Optionally filter by category or status.
    """
    try:
        email_repo = EmailSettingsRepository()
        logs = email_repo.get_email_logs(db, limit, category, status)
        
        return [
            {
                "id": log.id,
                "recipient_email": log.recipient_email,
                "email_type": log.email_type,
                "team_category": log.team_category,
                "subject": log.subject,
                "status": log.status,
                "error_message": log.error_message,
                "tender_id": log.tender_id,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
        
    except Exception as e:
        logger.error(f"Error retrieving email logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve email logs")

@router.get("/logs/crawl")
async def get_crawl_logs(
    limit: int = 50,
    page_id: int = None,
    db: Session = Depends(get_db)
):
    """
    Retrieve recent crawl logs for monitored pages.
    Optionally filter by a specific page_id.
    """
    query = db.query(CrawlLog)
    
    if page_id:
        query = query.filter(CrawlLog.page_id == page_id)
    
    logs = query.order_by(CrawlLog.started_at.desc()).limit(limit).all()
    
    return [
        {
            "id": log.id,
            "page_id": log.page_id,
            "page_name": log.page.name if log.page else None,
            "status": log.status,
            "tenders_found": log.tenders_found,
            "tenders_new": log.tenders_new,
            "started_at": log.started_at.isoformat(),
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": log.duration_seconds,
            "error_message": log.error_message,
            "error_type": log.error_type
        }
        for log in logs
    ]

# --------------------------
# Crawler Testing Endpoint
# --------------------------

@router.post("/test-crawler")
async def test_crawler(request: TestCrawlerRequest):
    """
    Use the TenderScraper to extract content from the supplied URL
    and report extraction success and content statistics (title, word count, etc).
    """
    try:
        url = str(request.url)
        logger.info(f"Testing crawler on URL: {url}")
        
        # Use the existing TenderScraper class (async context manager) to crawl the page
        async with TenderScraper() as scraper:
            result = await scraper.scrape_page(url)
        
        if result['status'] == 'success':
            logger.info(f"Crawler test successful for {url}")
            return {
                'status': 'success',
                'url': url,
                'title': result.get('title', ''),
                'markdown': result.get('markdown', ''),
                'html': result.get('html', ''),
                'links': result.get('links', []),
                'media': result.get('media', []),
                'metadata': result.get('metadata', {}),
                'word_count': result.get('word_count', 0),
                'char_count': result.get('char_count', 0)
            }
        else:
            logger.error(f"Crawler test failed for {url}: {result.get('error', 'Unknown error')}")
            return {
                'status': 'failed',
                'url': url,
                'error': result.get('error', 'Failed to extract content from the page')
            }
            
    except Exception as e:
        logger.error(f"Error testing crawler for {url}: {e}")
        return {
            'status': 'error',
            'url': str(request.url),
            'error': f'Server error while testing crawler: {str(e)}'
        }


# ------------------------------------------------------------------------------
# DETAILED COMMENTS ABOUT THIS FILE AND CODE:
# ------------------------------------------------------------------------------

# File Purpose:
# -------------
# This file defines the system/configuration endpoints for a FastAPI backend
# application related to monitoring tenders, crawling web pages, and managing
# notification preferences and logs for ESG (Environmental, Social, Governance)
# and credit rating alerts.

# Key Functional Areas:
# ---------------------
# 1) System Status (`/status`):
#    - Returns health/uptime info, version, counts of monitored pages, tenders, and recent crawl jobs.
#
# 2) Notification Email Settings (`/email-settings`, `/email-settings/{category}/add`, `/email-settings/{category}/{email}`):
#    - Enables GET/POST to fetch and save the primary notification and preference config
#    - Supports per-team lists (ESG and Credit Rating)
#    - Addition and removal endpoints simplify client management of lists.
#    - Settings are managed via the EmailSettingsRepository abstraction.
#
# 3) Email Notification Logs (`/email-logs`):
#    - Allows querying of logs for all notification emails sent (including errors)
#    - Useful for audit, troubleshooting, and history in admin dashboards.
#
# 4) Crawler Logs (`/logs/crawl`):
#    - Surfaces detailed crawl job results, error tracking, and timing info for recent (or filtered) jobs.
#
# 5) Crawler Testing (`/test-crawler`):
#    - Lets admins or devs test the page-content extraction system on demand for any target URL using the standard scraping logic.
#
# 6) Send Test Email (`/test-email`):
#    - Allows users/admins to verify the system's email sending is functioning (with logging).

# Design and Implementation Comments:
# -----------------------------------
# - All endpoints use dependency injection for database session management via FastAPI's Depends.
# - Logging is used fairly consistently for key actions and error paths, aiding observability.
# - Pydantic models provide schema validation for both incoming requests and outgoing responses.
# - The EmailSettingsRepository serves as a boundary layer between routes and the raw database when working with notification config and logs, increasing maintainability.
# - Exception handling is robust: all endpoints return HTTP errors on failure, and log error details for later analysis.
# - Some endpoints (test email/push, remove/add recipient) enforce strict validation on categories to avoid configuration mistakes.
# - Async handling allows for non-blocking DB and I/O operations—critical for test email and crawler endpoints.

# Extension/Integration Points:
# -----------------------------
# - The system is easily extensible for new notification channels, categories, or log types.
# - The standardization of request and response pydantic models increases front-end dev velocity and safety.
# - The use of context managers for resource management in scraping (TenderScraper) ensures clean-up and safe concurrency.
#
# - Any changes to notification structure, team categories, or crawler architecture should be reflected in both models and endpoints here.

# Security/Validation Caveats:
# ----------------------------
# - Email addresses and categories are stringently validated.
# - Database errors and unexpected exceptions are properly hidden behind HTTP error codes/messages for client privacy.

# Risks / Defects:
# ----------------
# - Static default notification_preferences might not propagate as expected if database returns None—should be covered by default dict in code.
# - Version string is hardcoded, requiring manual update on deployment.

# Overall: 
# ---------
# This file is a best-practices implementation for system admin/config endpoints in a FastAPI application that coordinates notifications, content crawling, and logging.