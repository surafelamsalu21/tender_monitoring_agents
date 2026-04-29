"""
Fixed Email Settings Repository
app/repositories/email_settings_repository.py
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import logging
import json

from app.models.email_settings import EmailNotificationSettings, EmailNotificationLog

logger = logging.getLogger(__name__)

class EmailSettingsRepository:
    """Repository for email settings database operations"""
    
    def get_email_settings(self, db: Session) -> Dict[str, Any]:
        """Get current email settings from database"""
        try:
            # Query settings from database
            esg_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'esg_emails'
            ).first()
            
            credit_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'credit_emails'
            ).first()
            
            prefs_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'preferences'
            ).first()
            
            return {
                'esg_emails': esg_setting.setting_value if esg_setting else [],
                'credit_rating_emails': credit_setting.setting_value if credit_setting else [],
                'notification_preferences': prefs_setting.setting_value if prefs_setting else {
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                }
            }
        except Exception as e:
            logger.error(f"Error retrieving email settings from database: {e}")
            # Return default settings if database query fails
            return {
                'esg_emails': [],
                'credit_rating_emails': [],
                'notification_preferences': {
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                }
            }
    
    def save_email_settings(self, db: Session, settings: Dict[str, Any]) -> bool:
        """Save email settings to database"""
        try:
            # Save or update ESG emails
            esg_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'esg_emails'
            ).first()
            
            if esg_setting:
                esg_setting.setting_value = settings.get('esg_emails', [])
                esg_setting.updated_at = datetime.utcnow()
            else:
                esg_setting = EmailNotificationSettings(
                    setting_key='esg_emails',
                    setting_value=settings.get('esg_emails', []),
                    description='ESG team email addresses for notifications'
                )
                db.add(esg_setting)
            
            # Save or update Credit Rating emails
            credit_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'credit_emails'
            ).first()
            
            if credit_setting:
                credit_setting.setting_value = settings.get('credit_rating_emails', [])
                credit_setting.updated_at = datetime.utcnow()
            else:
                credit_setting = EmailNotificationSettings(
                    setting_key='credit_emails',
                    setting_value=settings.get('credit_rating_emails', []),
                    description='Credit Rating team email addresses for notifications'
                )
                db.add(credit_setting)
            
            # Save or update preferences
            prefs_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'preferences'
            ).first()
            
            if prefs_setting:
                prefs_setting.setting_value = settings.get('notification_preferences', {})
                prefs_setting.updated_at = datetime.utcnow()
            else:
                prefs_setting = EmailNotificationSettings(
                    setting_key='preferences',
                    setting_value=settings.get('notification_preferences', {}),
                    description='Email notification preferences and settings'
                )
                db.add(prefs_setting)
            
            db.commit()
            logger.info("Email settings saved successfully to database")
            return True
            
        except Exception as e:
            logger.error(f"Error saving email settings to database: {e}")
            db.rollback()
            return False
    
    def get_emails_by_category(self, db: Session, category: str) -> List[str]:
        """Get email addresses for a specific category"""
        try:
            setting_key = 'esg_emails' if category == 'esg' else 'credit_emails'
            
            setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == setting_key
            ).first()
            
            if setting and setting.setting_value:
                return setting.setting_value
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error retrieving emails for category {category}: {e}")
            return []
    
    def add_email_to_category(self, db: Session, category: str, email: str) -> bool:
        """Add email to specific category - FIXED VERSION"""
        try:
            setting_key = 'esg_emails' if category == 'esg' else 'credit_emails'
            
            setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == setting_key
            ).first()
            
            if setting:
                # Get current emails list
                current_emails = setting.setting_value or []
                
                # Add new email if not already present
                if email not in current_emails:
                    current_emails.append(email)
                    setting.setting_value = current_emails
                    setting.updated_at = datetime.utcnow()
                    logger.info(f"Adding email {email} to existing {category} category")
                else:
                    logger.info(f"Email {email} already exists in {category} category")
                    return True  # Still return True since email is in the list
            else:
                # Create new setting with this email
                setting = EmailNotificationSettings(
                    setting_key=setting_key,
                    setting_value=[email],
                    description=f'{category.upper()} team email addresses for notifications'
                )
                db.add(setting)
                logger.info(f"Creating new {category} category with email {email}")
            
            db.commit()
            logger.info(f"Successfully added email {email} to {category} category")
            return True
            
        except Exception as e:
            logger.error(f"Error adding email to category: {e}")
            db.rollback()
            return False
    
    def remove_email_from_category(self, db: Session, category: str, email: str) -> bool:
        """Remove email from specific category - FIXED VERSION"""
        try:
            setting_key = 'esg_emails' if category == 'esg' else 'credit_emails'
            
            setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == setting_key
            ).first()
            
            if setting and setting.setting_value:
                current_emails = setting.setting_value
                if email in current_emails:
                    current_emails.remove(email)
                    setting.setting_value = current_emails
                    setting.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Removed email {email} from {category} category")
                else:
                    logger.info(f"Email {email} not found in {category} category")
            else:
                logger.info(f"No settings found for {category} category")
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing email from category: {e}")
            db.rollback()
            return False
    
    def log_email_notification(self, db: Session, recipient_email: str, email_type: str, 
                             team_category: str, subject: str, status: str, 
                             error_message: str = None, tender_id: int = None) -> bool:
        """Log email notification attempt"""
        try:
            log_entry = EmailNotificationLog(
                recipient_email=recipient_email,
                email_type=email_type,
                team_category=team_category,
                subject=subject,
                status=status,
                error_message=error_message,
                tender_id=tender_id
            )
            
            db.add(log_entry)
            db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error logging email notification: {e}")
            db.rollback()
            return False
    
    def get_email_logs(self, db: Session, limit: int = 50, 
                      category: str = None, status: str = None) -> List[EmailNotificationLog]:
        """Get email notification logs"""
        try:
            query = db.query(EmailNotificationLog)
            
            if category:
                query = query.filter(EmailNotificationLog.team_category == category)
            
            if status:
                query = query.filter(EmailNotificationLog.status == status)
            
            logs = query.order_by(EmailNotificationLog.sent_at.desc()).limit(limit).all()
            return logs
            
        except Exception as e:
            logger.error(f"Error retrieving email logs: {e}")
            return []
    
    def get_notification_preferences(self, db: Session) -> Dict[str, bool]:
        """Get notification preferences"""
        try:
            prefs_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'preferences'
            ).first()
            
            if prefs_setting and prefs_setting.setting_value:
                return prefs_setting.setting_value
            else:
                return {
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                }
                
        except Exception as e:
            logger.error(f"Error retrieving notification preferences: {e}")
            return {
                "send_for_new_tenders": True,
                "send_daily_summary": True,
                "send_urgent_notifications": True
            }