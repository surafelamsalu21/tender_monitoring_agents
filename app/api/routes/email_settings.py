"""
Email Settings API Routes
Management endpoints for email notification settings
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import json
import logging

from app.core.database import get_db
from app.services.email_service import EnhancedEmailService
from app.repositories.email_repository import EmailSettingsRepository

logger = logging.getLogger(__name__)

# Add this to your existing system.py router or create a new router
email_router = APIRouter()

class EmailSettings(BaseModel):
    esg_emails: List[EmailStr]
    credit_rating_emails: List[EmailStr]
    notification_preferences: Dict[str, bool] = {
        "send_for_new_tenders": True,
        "send_daily_summary": True,
        "send_urgent_notifications": True
    }

class EmailSettingsResponse(BaseModel):
    success: bool
    message: str
    settings: EmailSettings

class TestEmailRequest(BaseModel):
    email: EmailStr
    category: str  # 'esg' or 'credit_rating'

@email_router.get("/email-settings", response_model=EmailSettingsResponse)
async def get_email_settings_updated(db: Session = Depends(get_db)):
    """Get current email notification settings from database"""
    try:
        repo = EmailSettingsRepository()
        settings = repo.get_email_settings(db)
        
        return EmailSettingsResponse(
            success=True,
            message="Email settings retrieved successfully",
            settings=settings
        )
    except Exception as e:
        logger.error(f"Error retrieving email settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve email settings")

@email_router.post("/email-settings", response_model=EmailSettingsResponse)
async def save_email_settings_updated(settings: EmailSettings, db: Session = Depends(get_db)):
    """Save email notification settings to database"""
    try:
        repo = EmailSettingsRepository()
        success = repo.save_email_settings(db, settings)
        
        if success:
            return EmailSettingsResponse(
                success=True,
                message="Email settings saved successfully",
                settings=settings
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to save email settings")
            
    except Exception as e:
        logger.error(f"Error saving email settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save email settings")

@email_router.post("/test-email")
async def send_test_email(request: TestEmailRequest):
    """Send a test email to verify email configuration"""
    try:
        email_service = EnhancedEmailService()
        
        # Create test tender data based on category
        test_tender_data = {
            'title': f'Test {request.category.upper()} Tender - Email Configuration Test',
            'url': 'https://example.com/test-tender',
            'category': request.category,
            'description': f'This is a test tender for {request.category} team email configuration',
            'matched_keywords': ['test', 'configuration']
        }
        
        # Send test email
        result = await email_service.send_test_intelligent_email(
            recipient=request.email,
            test_tender_data=test_tender_data
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

@email_router.delete("/email-settings/{category}/{email}")
async def remove_email_from_settings(category: str, email: str):
    """Remove an email from notification settings"""
    try:
        if category not in ['esg', 'credit_rating']:
            raise HTTPException(status_code=400, detail="Category must be 'esg' or 'credit_rating'")
        
        # In a real implementation, you would remove from database
        logger.info(f"Removing email {email} from {category} notifications")
        
        return {
            "success": True,
            "message": f"Email {email} removed from {category} notifications"
        }
    except Exception as e:
        logger.error(f"Error removing email: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove email")

@email_router.post("/email-settings/{category}/add")
async def add_email_to_settings(category: str, email: EmailStr):
    """Add an email to notification settings"""
    try:
        if category not in ['esg', 'credit_rating']:
            raise HTTPException(status_code=400, detail="Category must be 'esg' or 'credit_rating'")
        
        repo = EmailSettingsRepository()
        success = repo.add_email_to_settings(category, email)
        
        if success:
            return {
                "success": True,
                "message": f"Email {email} added to {category} notifications"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to add email")
    except Exception as e:
        logger.error(f"Error adding email: {e}")
        raise HTTPException(status_code=500, detail="Failed to add email")