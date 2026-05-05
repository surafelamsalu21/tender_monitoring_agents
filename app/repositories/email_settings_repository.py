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

LEGACY_EMAIL_SETTING_KEYS = frozenset({"esg_emails", "credit_emails"})


class EmailSettingsRepository:
    """Repository for email settings database operations"""

    def migrate_legacy_email_notification_settings(self, db: Session) -> None:
        """Merge legacy team lists into opportunity_emails and delete legacy rows."""
        legacy_rows = (
            db.query(EmailNotificationSettings)
            .filter(EmailNotificationSettings.setting_key.in_(LEGACY_EMAIL_SETTING_KEYS))
            .all()
        )
        if not legacy_rows:
            return

        opp = (
            db.query(EmailNotificationSettings)
            .filter(EmailNotificationSettings.setting_key == "opportunity_emails")
            .first()
        )
        merged: List[str] = []
        if opp and opp.setting_value:
            merged = list(opp.setting_value)
        for row in legacy_rows:
            if row.setting_value:
                merged.extend(row.setting_value)
        merged = list(dict.fromkeys(merged))

        if opp:
            opp.setting_value = merged
            opp.updated_at = datetime.utcnow()
        else:
            db.add(
                EmailNotificationSettings(
                    setting_key="opportunity_emails",
                    setting_value=merged,
                    description="Recipients for opportunity screening notifications",
                )
            )
        for row in legacy_rows:
            db.delete(row)
        db.commit()
        logger.info("Migrated legacy notification email rows into opportunity_emails")

    def get_email_settings(self, db: Session) -> Dict[str, Any]:
        """Get current email settings from database"""
        try:
            self.migrate_legacy_email_notification_settings(db)

            opportunity_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'opportunity_emails'
            ).first()
            
            prefs_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'preferences'
            ).first()
            
            opportunity_emails = (
                list(opportunity_setting.setting_value)
                if opportunity_setting and opportunity_setting.setting_value
                else []
            )

            return {
                'opportunity_emails': opportunity_emails,
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
                'opportunity_emails': [],
                'notification_preferences': {
                    "send_for_new_tenders": True,
                    "send_daily_summary": True,
                    "send_urgent_notifications": True
                }
            }
    
    def save_email_settings(self, db: Session, settings: Dict[str, Any]) -> bool:
        """Save email settings to database"""
        try:
            self.migrate_legacy_email_notification_settings(db)

            # Save or update unified opportunity recipient list.
            opportunity_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == 'opportunity_emails'
            ).first()

            if opportunity_setting:
                opportunity_setting.setting_value = settings.get('opportunity_emails', [])
                opportunity_setting.updated_at = datetime.utcnow()
            else:
                opportunity_setting = EmailNotificationSettings(
                    setting_key='opportunity_emails',
                    setting_value=settings.get('opportunity_emails', []),
                    description='Recipients for opportunity screening notifications'
                )
                db.add(opportunity_setting)
            
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
            setting_key = "opportunity_emails"
            if category not in ["screening_opportunities", "opportunity", "opportunities"]:
                # Legacy support: map older categories to unified recipient list.
                setting_key = "opportunity_emails"

            setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == setting_key
            ).first()

            if setting and setting.setting_value:
                return setting.setting_value

            # Backward compatibility while old keys still exist in DB.
            esg_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == "esg_emails"
            ).first()
            credit_setting = db.query(EmailNotificationSettings).filter(
                EmailNotificationSettings.setting_key == "credit_emails"
            ).first()
            esg_emails = esg_setting.setting_value if esg_setting and esg_setting.setting_value else []
            credit_emails = credit_setting.setting_value if credit_setting and credit_setting.setting_value else []
            return list(dict.fromkeys([*esg_emails, *credit_emails]))

        except Exception as e:
            logger.error(f"Error retrieving emails for category {category}: {e}")
            return []
    
    def add_email_to_category(self, db: Session, category: str, email: str) -> bool:
        """Add email to specific category - FIXED VERSION"""
        try:
            self.migrate_legacy_email_notification_settings(db)
            setting_key = "opportunity_emails"
            
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
                    logger.info(f"Adding email {email} to opportunity screening recipient list ({category})")
                else:
                    logger.info(f"Email {email} already exists in {category} recipient list")
                    return True  # Still return True since email is in the list
            else:
                # Create new setting with this email
                setting = EmailNotificationSettings(
                    setting_key=setting_key,
                    setting_value=[email],
                    description="Recipients for opportunity screening notifications",
                )
                db.add(setting)
                logger.info(f"Creating new recipient list with email {email}")
            
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
            self.migrate_legacy_email_notification_settings(db)
            setting_key = "opportunity_emails"
            
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