"""
Updated Database Initialization with Email Settings
Add this to your existing app/core/init_data.py
"""
import logging
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import MonitoredPage, Keyword
from app.models.email_settings import EmailNotificationSettings, EmailNotificationLog
from app.repositories.page_repository import PageRepository
from app.repositories.keyword_repository import KeywordRepository
from app.repositories.email_settings_repository import EmailSettingsRepository

logger = logging.getLogger(__name__)

def initialize_default_data():
    """Initialize default pages, keywords, and email settings"""
    db = SessionLocal()
    try:
        page_repo = PageRepository()
        keyword_repo = KeywordRepository()
        email_repo = EmailSettingsRepository()
        
        # Initialize default monitored page
        existing_page = page_repo.get_page_by_url(db, "https://corp.uzairways.com/ru/press-center/tenders")
        if not existing_page:
            page_repo.create_page(
                db,
                name="Uzbekistan Airways Tenders",
                url="https://corp.uzairways.com/ru/press-center/tenders",
                description="Official tender page for Uzbekistan Airways",
                crawl_frequency_hours=3
            )
            logger.info("Created default monitored page: Uzbekistan Airways")
        
        # Initialize ESG keywords
        esg_keywords = [
            "environmental", "sustainability", "green", "carbon", "climate", 
            "renewable", "social responsibility", "governance", "ESG"
        ]
        
        for keyword in esg_keywords:
            existing = db.query(Keyword).filter(
                Keyword.keyword == keyword,
                Keyword.category == "esg"
            ).first()
            
            if not existing:
                keyword_repo.create_keyword(
                    db,
                    keyword=keyword,
                    category="esg",
                    description=f"ESG keyword: {keyword}"
                )
        
        # Initialize Credit Rating keywords
        credit_keywords = [
            "credit rating""risk", "assessment", 
            "creditworthiness"
        ]
        
        for keyword in credit_keywords:
            existing = db.query(Keyword).filter(
                Keyword.keyword == keyword,
                Keyword.category == "credit_rating"
            ).first()
            
            if not existing:
                keyword_repo.create_keyword(
                    db,
                    keyword=keyword,
                    category="credit_rating",
                    description=f"Credit rating keyword: {keyword}"
                )
        
        # Initialize email settings (NEW)
        logger.info("Initializing email settings...")
        
        # Check if email settings already exist
        existing_esg = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == 'esg_emails'
        ).first()
        
        if not existing_esg:
            logger.info("Creating default email settings...")
            
            # Create default ESG emails setting
            default_esg = EmailNotificationSettings(
                setting_key='esg_emails',
                setting_value=[],  # Start with empty list
                description='ESG team email addresses for notifications'
            )
            db.add(default_esg)
            
            # Create default Credit Rating emails setting
            default_credit = EmailNotificationSettings(
                setting_key='credit_emails',
                setting_value=[],  # Start with empty list
                description='Credit Rating team email addresses for notifications'
            )
            db.add(default_credit)
            
            # Create default preferences
            default_prefs = EmailNotificationSettings(
                setting_key='preferences',
                setting_value={
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                },
                description='Email notification preferences and settings'
            )
            db.add(default_prefs)
            
            db.commit()
            logger.info("Email settings initialized successfully")
        else:
            logger.info("Email settings already exist")
        
        logger.info("Default data initialization completed")
        
    except Exception as e:
        logger.error(f"Error initializing default data: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def initialize_email_settings_only():
    """Initialize only email settings (helper function)"""
    db = SessionLocal()
    try:
        logger.info("Initializing email settings...")
        
        # Check if email settings already exist
        existing_esg = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == 'esg_emails'
        ).first()
        
        if not existing_esg:
            logger.info("Creating email settings tables and default data...")
            
            # Create default ESG emails setting
            default_esg = EmailNotificationSettings(
                setting_key='esg_emails',
                setting_value=[],
                description='ESG team email addresses for notifications'
            )
            db.add(default_esg)
            
            # Create default Credit Rating emails setting
            default_credit = EmailNotificationSettings(
                setting_key='credit_emails', 
                setting_value=[],
                description='Credit Rating team email addresses for notifications'
            )
            db.add(default_credit)
            
            # Create default preferences
            default_prefs = EmailNotificationSettings(
                setting_key='preferences',
                setting_value={
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                },
                description='Email notification preferences and settings'
            )
            db.add(default_prefs)
            
            db.commit()
            logger.info("✅ Email settings initialized successfully")
            return True
        else:
            logger.info("✅ Email settings already exist")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error initializing email settings: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    # Test email settings initialization
    logging.basicConfig(level=logging.INFO)
    
    print("Initializing email settings...")
    success = initialize_email_settings_only()
    
    if success:
        print("✅ Email settings initialized successfully!")
    else:
        print("❌ Failed to initialize email settings")