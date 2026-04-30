# app/models/__init__.py - Add email settings models

from .page import MonitoredPage
from .tender import Tender, DetailedTender
from .keyword import Keyword
from .crawl_log import CrawlLog
from .email_settings import EmailNotificationSettings, EmailNotificationLog
from .user import User

__all__ = [
    'MonitoredPage',
    'Tender', 
    'DetailedTender',
    'Keyword',
    'CrawlLog',
    'EmailNotificationSettings',
    'EmailNotificationLog',
    'User',
]

# ------------------------------------------------------------------------------
# This file imports and exposes all database model classes for the application.
# It includes models for pages, tenders, keywords, crawl logs, and email settings.
# The __all__ list ensures only relevant classes are exported on import.
# Other modules can import any model from this file for unified access.
# Keeps model imports organized and centralized for app-wide use.
# Updating this file updates model visibility everywhere in the project.
# ------------------------------------------------------------------------------