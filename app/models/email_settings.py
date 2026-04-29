"""
Email Settings Database Model
Create this as app/models/email_settings.py
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text
from datetime import datetime

from app.core.database import Base

class EmailNotificationSettings(Base):
    """
    ORM model representing persistent settings for email notification configuration.

    Stores generic key-value (JSON) pairs for:
        - Notification recipient lists (per team/category)
        - Preferences or feature toggles
        - Potentially other future email-related configuration

    Schema:
        - id (int): Primary key for unique identification.
        - setting_key (str): Name/key describing this setting ('esg_emails', 'credit_emails', 'preferences', ...),
          must be unique.
        - setting_value (json): Value of this setting, may be an array (e.g. emails) or an object
          (e.g. preferences dict).
        - description (str): Human-friendly description for admins (optional).
        - created_at (datetime): Timestamp when this settings record was created.
        - updated_at (datetime): Timestamp for last modification.

    Usage:
        - Allows dynamic addition/editing of email settings from admin UI or scripts.
        - Enables team/category-specific notifications with arbitrary storage format.
    """
    __tablename__ = "email_notification_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), nullable=False, unique=True, index=True)  # 'esg_emails', 'credit_emails', 'preferences'
    setting_value = Column(JSON, nullable=False)  # JSON array (for emails) or object (for preferences)
    description = Column(Text, nullable=True)  # Human-readable explanation
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<EmailNotificationSettings(key='{self.setting_key}', value='{self.setting_value}')>"

class EmailNotificationLog(Base):
    """
    ORM model for logging each email notification event sent by the application.

    Each record is an audit entry documenting a single email notification attempt.

    Schema:
        - id (int): Primary key for unique identification.
        - recipient_email (str): Target email address.
        - email_type (str): Nature of the email ('new_tender', 'daily_summary', 'test', etc.)
        - team_category (str): Category of the team/notification
          (e.g., 'esg', 'credit_rating').
        - subject (str): Subject line of the email (may be null if failed early).
        - status (str): Delivery result ('sent', 'failed', 'pending', etc.).
        - error_message (str): Text describing error, if any (optional).
        - tender_id (int): (Optional) Link to associated tender if relevant.
        - sent_at (datetime): When the email was sent (or attempted).
        - created_at (datetime): Timestamp for audit/tracing.

    Usage:
        - Persistent audit trail of notification activity,
          including delivery outcome and problem diagnostics.
        - Facilitates debugging, compliance, and support for user claims.
        - Allows easy review of which users were notified for which events.
    """
    __tablename__ = "email_notification_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    recipient_email = Column(String(255), nullable=False, index=True)
    email_type = Column(String(50), nullable=False, index=True)  # 'new_tender', 'daily_summary', 'test', etc.
    team_category = Column(String(50), nullable=False, index=True)  # 'esg', 'credit_rating'
    subject = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, index=True)  # 'sent', 'failed', 'pending'
    error_message = Column(Text, nullable=True)
    
    # Related data
    tender_id = Column(Integer, nullable=True)  # Optional: Link to tender if applicable
    
    # Metadata
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<EmailNotificationLog(id={self.id}, recipient='{self.recipient_email}', status='{self.status}')>"

# ==========================================================================================
# DETAILED COMMENTS ABOUT THIS CODE AND FILE:
#
# Purpose & Context:
# - This file defines two SQLAlchemy ORM models for managing and auditing all aspects
#   of email notifications in the application.
# - It supports robust, flexible notification configuration and full traceability of
#   email delivery for reliability, compliance, and debugging.
#
# Structure:
# 1) EmailNotificationSettings:
#    - This table acts as a dynamic key-value/config storage for anything related
#      to email notifications (such as recipient lists, per-category settings, and
#      notification preferences).
#    - By using a generic JSON value, it allows future extension without schema changes.
#    - The `setting_key` must be unique, supporting direct lookup and update by key.
#
# 2) EmailNotificationLog:
#    - Designed to log every notification delivery or attempt made by the application.
#    - Records recipient, notification type (purpose), status/result, relevant team/category,
#      associated tender (if any), timing, and errors.
#    - Enables application administrators and support to audit who was (or was not)
#      contacted and diagnose any failed or problematic email attempts.
#    - The presence of timestamps, error info, and type/category tags
#      enables rich filtering and reporting downstream.
#
# Usage Across Application:
# - EmailNotificationSettings:
#     • Used for CRUD of notification preferences and dynamic modification of recipient groups
#     • Backing model for UI that configures notifications for teams, categories, or general/global events
# - EmailNotificationLog:
#     • Powering status dashboards, delivery error monitoring, and compliance export
#     • Supports finding all actions taken/not taken for a particular user, team, or event
#
# Extensibility & Best Practice:
# - The use of JSON in settings maximizes flexibility.
# - Separate logging ensures both configuration and actual outcomes are persistently tracked.
# - Detailed string field length, timestamp defaults, and reproducible __repr__ methods
#   all aid in clarity and ease of debugging or migration.
#
# File Organization:
# - Mirroring the pattern and commenting style used for other models in app/models/.
# - Sufficient documentation is in docstrings and at the bottom for maintainers and auditors.
#
# ==========================================================================================