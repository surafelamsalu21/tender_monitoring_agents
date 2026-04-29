"""
Crawl Log Database Model
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base

class CrawlLog(Base):
    """
    The CrawlLog model represents a record of a crawling event/activity on a monitored page.
    
    Each instance is a single attempt (or scheduled run) to crawl data from a MonitoredPage.
    This log is critical for tracking crawling health, errors, coverage, and discovering systemic
    or transient crawling issues over time.
    """
    __tablename__ = "crawl_logs"
    
    # ---------- Primary Key ----------
    id = Column(Integer, primary_key=True, index=True)
    
    # ---------- Foreign Keys & Relationships ----------
    page_id = Column(Integer, ForeignKey("monitored_pages.id"), nullable=False)
    page = relationship("MonitoredPage", back_populates="crawl_logs")
    
    # ---------- Crawl Details ----------
    status = Column(String(50), nullable=False, index=True)  # e.g., 'success', 'failed', 'partial'
    tenders_found = Column(Integer, default=0)               # How many total tenders were detected on this crawl
    tenders_new = Column(Integer, default=0)                 # How many tenders were new/previously unseen
    
    # ---------- Timing Information ----------
    started_at = Column(DateTime, default=datetime.utcnow, index=True)  # When this crawl began
    completed_at = Column(DateTime, nullable=True)                     # When finished (if finished)
    duration_seconds = Column(Integer, nullable=True)                  # Optionally set (redundant to duration property)
    
    # ---------- Error Reporting ----------
    error_message = Column(Text, nullable=True)         # Long error message, details if failed
    error_type = Column(String(100), nullable=True)     # Short error _type_ (exception class, etc.)
    
    # ---------- Methods & Properties ----------
    def __repr__(self):
        """String representation for debugging/logging."""
        return f"<CrawlLog(id={self.id}, page_id={self.page_id}, status='{self.status}', tenders_found={self.tenders_found})>"
    
    @property
    def duration(self) -> int:
        """
        Calculate the crawl duration in seconds (if both completed_at and started_at are present).
        Returns 0 if incomplete or missing timestamps.
        """
        if self.completed_at and self.started_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return 0

# ==========================================================================================
# DETAILED COMMENTS ABOUT THIS CODE AND FILE:
#
# Purpose & Role:
# - This file defines the SQLAlchemy ORM model for logging every crawl attempt against any
#   monitored page in the application. It provides a durable audit trail of crawling activity
#   and outcomes, enabling root-cause analysis, trend monitoring, and reliability tracking.
#
# Structure & Fields:
# - Each CrawlLog instance links to a MonitoredPage (via `page_id`), indicating which site/page was crawled.
# - Key crawl performance stats are tracked: number of tenders found and number which are new.
# - The model records the `status` (success/failed/partial/etc), allowing downstream logic to
#   filter/rank/summarize performance or errors.
# - Timing is covered by automatic `started_at`, optional `completed_at`, and a redundant/optional
#   `duration_seconds` field. There is also a computed `duration` property for convenience.
# - Errors are documented via a short error type and a long-form error message (if any).
#
# Relationships:
# - There is a foreign key to the "monitored_pages" table, with a SQLAlchemy relationship
#   for bidirectional querying from both crawls and pages.
#
# Application Usage:
# - The model is used for monitoring, alerting, debugging, and for auditing system performance
#   (to understand what pages fail most, or how crawl performance is trending).
# - It's foundational for dashboards, uptime checks, and reliability automation.
#
# Extensibility:
# - Additional analytics (e.g., memory/CPU, request count, etc.) could be added here if required.
#   See the current structure for best practice placement of new stats or diagnostic fields.
#
# File Conventions:
# - Comments and docstrings strictly explain the intent, context, and wiring for maintainability.
# - All SQLAlchemy fields and relationships are clearly named.
#
# ==========================================================================================