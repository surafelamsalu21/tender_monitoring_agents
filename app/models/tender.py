"""
Enhanced Tender Database Models with Keyword Tracking
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, JSON, Table
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base

# Association table for many-to-many relationship between tenders and matched keywords
tender_keywords = Table(
    'tender_keywords',
    Base.metadata,
    Column('tender_id', Integer, ForeignKey('tenders.id'), primary_key=True),  # FK to Tender, part of composite PK
    Column('keyword_id', Integer, ForeignKey('keywords.id'), primary_key=True),  # FK to Keyword, part of composite PK
    Column('created_at', DateTime, default=datetime.utcnow)  # Timestamp for association row creation
)

class Tender(Base):
    """
    Database model for a single tender, enhanced with keyword tracking and page linkage.

    Represents the primary tender data entity. Each Tender:
        - Has a unique title and URL.
        - Is categorized by a 'category' (e.g., esg, credit_rating).
        - Supports rich text description and date fields.
        - Tracks which keywords matched this tender (for filtering/search/notifications).
        - Maintains both explicit many-to-many relation (matched_keywords)
          and a JSON of matched keyword strings for efficiency and easy API serialization.
        - ForeignKey to MonitoredPage indicating which page this tender was scraped from.
        - Tracks its notification and processing status, as well as creation/update timestamps.
        - Has a one-to-one (uselist=False) relationship with a DetailedTender record for
          extended detail scraped/analyzed later.
    """
    __tablename__ = "tenders"
    
    id = Column(Integer, primary_key=True, index=True)  # Tender PK
    title = Column(String(500), nullable=False, index=True)  # Tender title, required
    url = Column(String(1000), nullable=False, unique=True, index=True)  # Unique URL to the tender resource
    tender_date = Column(DateTime, nullable=True, index=True)  # Optional date of tender issuance/submission
    category = Column(String(50), nullable=False, index=True)  # 'esg', 'credit_rating', or 'both'
    description = Column(Text, nullable=True)  # Raw description
    
    # Matched keyword information (JSON for API, count for fast filters/stats)
    matched_keywords_json = Column(JSON, nullable=True)  # List of matched keyword strings (JSON-serializable)
    keyword_count = Column(Integer, default=0)  # Number of keywords matched (for quick checks)
    
    # Foreign key/relationship to MonitoredPage (origin/source)
    page_id = Column(Integer, ForeignKey("monitored_pages.id"), nullable=False)
    page = relationship("MonitoredPage", back_populates="tenders")

    # One-to-one relationship: Each tender can have extended details parsed later
    detailed_tender = relationship("DetailedTender", back_populates="tender", uselist=False)
    
    # Many-to-many relationship with keywords (see association table above)
    matched_keywords = relationship(
        "Keyword", 
        secondary=tender_keywords, 
        back_populates="tenders_using_keyword"
    )
    
    # State tracking and metadata
    is_processed = Column(Boolean, default=False, index=True)  # For deduplication/workflow state
    is_notified = Column(Boolean, default=False, index=True)  # Whether notification has been sent
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # Creation timestamp
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Last update timestamp
    
    def __repr__(self):
        # Displays a short summary useful for debugging: id, abbreviated title, category, and keyword count
        return f"<Tender(id={self.id}, title='{self.title[:50]}...', category='{self.category}', keywords={self.keyword_count})>"

class DetailedTender(Base):
    """
    Stores detailed/augmented information about a tender, 
    often generated later by a scraping/AI Agent.

    Each DetailedTender is associated with exactly one Tender:
        - Contains additional fields (detailed_title, description, requirements, etc.).
        - Optionally stores AI-generated fields and full page content as text or JSON.
        - Tracks status of detailed data gathering (processing_status) and validation results (date_validation).
        - Timestamps for tracking scraping/processing lifecycle.
    """
    __tablename__ = "detailed_tenders"
    
    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"), nullable=False, unique=True)  # One-to-one link to Tender

    # Detailed tender data (may be AI or scrape-derived, not always present at initial tender ingest)
    detailed_title = Column(String(1000), nullable=True)  # Augmented/clarified title
    detailed_description = Column(Text, nullable=True)    # Enriched or normalized description
    requirements = Column(Text, nullable=True)            # Requirements parsed/summarized
    deadline = Column(DateTime, nullable=True)            # Deadline if parsed
    contact_info = Column(Text, nullable=True)            # Extracted contact information
    additional_details = Column(Text, nullable=True)      # Free-form extra info

    full_content = Column(Text, nullable=True)            # Raw page text or HTML content dump
    
    # Processing metadata
    processing_status = Column(String(50), default="pending")  # Status: pending, processed, partial, failed, etc.
    ai_response = Column(JSON, nullable=True)              # Raw AI or agent model response, if used

    date_validation = Column(JSON, nullable=True)          # Stores validation or extraction results for time/date

    # Relationship back to Tender (inverse of one-to-one link above)
    tender = relationship("Tender", back_populates="detailed_tender")
    
    # Metadata timestamps
    created_at = Column(DateTime, default=datetime.utcnow)  # Creation
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Modified
    processed_at = Column(DateTime, nullable=True)          # When successfully processed

    def __repr__(self):
        # Helpful string for debugging: id, associated tender id, and processing status
        return f"<DetailedTender(id={self.id}, tender_id={self.tender_id}, status='{self.processing_status}')>"

################################################################################
# Detailed Commentary: app/models/tender.py
################################################################################
#
# Purpose:
#   - Defines the SQLAlchemy ORM models for representing tenders (procurement notices, ESG, or credit rating opportunities) and the extended details about each tender.
#   - Supports efficient keyword tracking for tenders, which allows the system to record which keywords matched a particular tender, both for display (JSON column) and for advanced relational queries (many-to-many through tender_keywords table).
#
# Main Components:
#   1. `tender_keywords` association table:
#        - Implements a many-to-many mapping between tenders and keywords, enabling fast queries such as "which tenders used this keyword" or "all keywords for this tender".
#        - Timestamp column ('created_at') provides an audit trail for when the association was made.
#   2. `Tender` model:
#        - Represents a single tender scraped from a monitored page.
#        - Storing both a JSON array of matched keyword strings (`matched_keywords_json`) and a normalized many-to-many relationship (`matched_keywords`) enables both fast API serialization and robust query capabilities.
#        - Connects each tender to its source `MonitoredPage` (via `page_id` and `page` relationship).
#        - Tracks crucial state for processing (ex: has this tender been already notified or processed?).
#        - Links (one-to-one) to a `DetailedTender` model for extra, full parsed/synthesized tender information.
#   3. `DetailedTender` model:
#        - Holds extended information, potentially generated asynchronously by an agent or parser after the base tender is found.
#        - Can store custom fields, AI output blobs, page content, advanced metadata, and validation output—allowing for flexible downstream processing.
#
# Relationships and Usage:
#       - Designed to support production workflows: initial scrape → tender ingest → keyword matching & notification → detailed scrape/AI → secondary processing.
#       - Efficiently models both simple queries (recent tenders, unnotified, tender by page) and advanced analytics (all tenders with X keywords, date validation statistics, full processing pipelines).
#       - Extensible: new fields for AI, validation, or keywords do not break the existing structure; supports future needs like keyword relevance ranking or notification retry logic.
#
# Key Coding Details:
#    - All models inherit from `Base` (SQLAlchemy declarative base).
#    - Timestamps default to current UTC.
#    - Use of `uselist=False` on detailed_tender relationship enforces 1:1.
#    - All foreign keys are indexed and enforce referential integrity.
#    - The `__repr__` methods provide helpful succinct debugging output.
#
# This file is central for all database CRUD involving tenders, for scraping input, 
# notification logic, page reporting, data analysis, and any process that operates on
# tenders or their matched keywords in the application.
################################################################################