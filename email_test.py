"""
Debug Email Settings - Check and Fix Database Issues
Run this script to diagnose and fix email settings problems
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import SessionLocal, engine
from app.models.email_settings import EmailNotificationSettings, EmailNotificationLog
from app.core.database import Base
from app.repositories.email_settings_repository import EmailSettingsRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_fix_email_settings():
    """Check database tables and email settings, fix issues"""
    
    print("=== Email Settings Diagnostic Tool ===\n")
    
    # Step 1: Check if tables exist
    print("1. Checking if email settings tables exist...")
    try:
        db = SessionLocal()
        
        # Try to query the email settings table
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='email_notification_settings'"))
        table_exists = result.fetchone() is not None
        
        if table_exists:
            print("✅ EmailNotificationSettings table exists")
        else:
            print("❌ EmailNotificationSettings table does NOT exist")
            print("   Creating tables now...")
            Base.metadata.create_all(bind=engine)
            print("✅ Tables created successfully")
        
        db.close()
    except Exception as e:
        print(f"❌ Error checking tables: {e}")
        return False
    
    # Step 2: Check current email settings in database
    print("\n2. Checking current email settings in database...")
    try:
        db = SessionLocal()
        email_repo = EmailSettingsRepository()
        
        # Get all email settings
        all_settings = db.query(EmailNotificationSettings).all()
        
        print(f"   Found {len(all_settings)} email settings entries:")
        for setting in all_settings:
            print(f"   - {setting.setting_key}: {setting.setting_value}")
        
        # Get emails by category
        esg_emails = email_repo.get_emails_by_category(db, 'esg')
        credit_emails = email_repo.get_emails_by_category(db, 'credit_rating')
        
        print(f"\n   ESG emails from repository: {esg_emails}")
        print(f"   Credit Rating emails from repository: {credit_emails}")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error checking email settings: {e}")
        return False
    
    # Step 3: Initialize default settings if empty
    print("\n3. Initializing default settings if needed...")
    try:
        db = SessionLocal()
        email_repo = EmailSettingsRepository()
        
        # Check if we have any settings
        esg_setting = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == 'esg_emails'
        ).first()
        
        if not esg_setting:
            print("   No ESG email settings found, creating default entries...")
            
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
            print("✅ Default email settings created")
        else:
            print("✅ Email settings already exist")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error initializing settings: {e}")
        return False
    
    # Step 4: Test adding sample emails
    print("\n4. Testing email addition...")
    try:
        db = SessionLocal()
        email_repo = EmailSettingsRepository()
        
        # Add test emails
        test_esg_email = "test-esg@company.com"
        test_credit_email = "test-credit@company.com"
        
        # Add ESG email
        success1 = email_repo.add_email_to_category(db, 'esg', test_esg_email)
        print(f"   Adding ESG email {test_esg_email}: {'✅ Success' if success1 else '❌ Failed'}")
        
        # Add Credit email
        success2 = email_repo.add_email_to_category(db, 'credit_rating', test_credit_email)
        print(f"   Adding Credit email {test_credit_email}: {'✅ Success' if success2 else '❌ Failed'}")
        
        # Verify emails were added
        esg_emails = email_repo.get_emails_by_category(db, 'esg')
        credit_emails = email_repo.get_emails_by_category(db, 'credit_rating')
        
        print(f"   ESG emails after addition: {esg_emails}")
        print(f"   Credit emails after addition: {credit_emails}")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error testing email addition: {e}")
        return False
    
    # Step 5: Test the email service
    print("\n5. Testing email service integration...")
    try:
        from app.services.email_service import EnhancedEmailService
        
        email_service = EnhancedEmailService()
        db = SessionLocal()
        
        # Test getting emails
        esg_emails = email_service.email_repo.get_emails_by_category(db, 'esg')
        credit_emails = email_service.email_repo.get_emails_by_category(db, 'credit_rating')
        
        print(f"   Email service ESG emails: {esg_emails}")
        print(f"   Email service Credit emails: {credit_emails}")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error testing email service: {e}")
        return False
    
    print("\n=== Diagnostic Complete ===")
    return True

def add_sample_emails():
    """Add some sample emails for testing"""
    print("\n=== Adding Sample Emails ===")
    
    try:
        db = SessionLocal()
        email_repo = EmailSettingsRepository()
        
        # Sample emails
        sample_emails = {
            'esg': [
                'esg-team@company.com',
                'sustainability@company.com',
                'environmental@company.com'
            ],
            'credit_rating': [
                'credit-team@company.com',
                'risk-assessment@company.com', 
                'financial-risk@company.com'
            ]
        }
        
        # Add ESG emails
        for email in sample_emails['esg']:
            success = email_repo.add_email_to_category(db, 'esg', email)
            print(f"Adding ESG email {email}: {'✅' if success else '❌'}")
        
        # Add Credit Rating emails
        for email in sample_emails['credit_rating']:
            success = email_repo.add_email_to_category(db, 'credit_rating', email)
            print(f"Adding Credit email {email}: {'✅' if success else '❌'}")
        
        # Verify final state
        esg_emails = email_repo.get_emails_by_category(db, 'esg')
        credit_emails = email_repo.get_emails_by_category(db, 'credit_rating')
        
        print(f"\nFinal ESG emails: {esg_emails}")
        print(f"Final Credit emails: {credit_emails}")
        
        db.close()
        print("✅ Sample emails added successfully!")
        
    except Exception as e:
        print(f"❌ Error adding sample emails: {e}")

def clear_all_emails():
    """Clear all emails (for testing)"""
    print("\n=== Clearing All Emails ===")
    
    try:
        db = SessionLocal()
        
        # Clear ESG emails
        esg_setting = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == 'esg_emails'
        ).first()
        if esg_setting:
            esg_setting.setting_value = []
            
        # Clear Credit emails
        credit_setting = db.query(EmailNotificationSettings).filter(
            EmailNotificationSettings.setting_key == 'credit_emails'
        ).first()
        if credit_setting:
            credit_setting.setting_value = []
        
        db.commit()
        db.close()
        print("✅ All emails cleared")
        
    except Exception as e:
        print(f"❌ Error clearing emails: {e}")

if __name__ == "__main__":
    print("Email Settings Debug Tool")
    print("1. Run diagnostic")
    print("2. Add sample emails") 
    print("3. Clear all emails")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        check_and_fix_email_settings()
    elif choice == "2":
        add_sample_emails()
    elif choice == "3":
        clear_all_emails()
    else:
        print("Running full diagnostic...")
        check_and_fix_email_settings()