"""
Email Settings Database Migration
Create this as a script: create_email_settings_tables.py
Run this to create the email settings tables in your database
"""
import logging
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models.email_settings import EmailNotificationSettings, EmailNotificationLog
from app.core.database import Base

logger = logging.getLogger(__name__)

def create_email_settings_tables():
    """Create email settings tables and initialize with default data"""
    try:
        # Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("Email settings tables created successfully")
        
        # Initialize with default settings
        db = SessionLocal()
        try:
            # Check if settings already exist
            existing_esg = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'esg_emails'
            ).first()
            
            if not existing_esg:
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
                logger.info("Default email settings initialized")
            else:
                logger.info("Email settings already exist, skipping initialization")
                
        except Exception as e:
            logger.error(f"Error initializing default email settings: {e}")
            db.rollback()
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error creating email settings tables: {e}")
        raise

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    print("Creating email settings tables...")
    create_email_settings_tables()
    print("Email settings tables created and initialized successfully!")

# Usage instructions:
"""
To use this migration:

1. Save this file as 'create_email_settings_tables.py' in your project root
2. Run: python create_email_settings_tables.py
3. Or add the function call to your existing initialization script

This will:
- Create the EmailNotificationSettings table
- Create the EmailNotificationLog table  
- Initialize default empty email lists for ESG and Credit Rating teams
- Set default notification preferences to True

After running this, your email settings will be stored in the database and 
the web interface will work with persistent data.
"""