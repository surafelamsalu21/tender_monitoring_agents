"""
Enhanced Keyword Database Model with Tender Relationships
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base

class Keyword(Base):
    """
    The Keyword model represents search or filter keywords
    used to categorize and track tenders within the system.

    Attributes:
        id (int): Primary key identifier for the keyword.
        keyword (str): The keyword string (max length 100, indexed).
        category (str): The category this keyword applies to (sector, activity_fit, geography, source_tag).
        description (str): Optional detailed description for the keyword.
        is_active (bool): Flag to indicate if the keyword is currently enabled/used.
        case_sensitive (bool): Whether keyword matching is case sensitive for this keyword.
        usage_count (int): Number of tenders that have matched this keyword (usage stats).
        last_used (datetime): Timestamp of the most recent match for this keyword.
        match_statistics (str): (Optional) JSON string containing additional match statistics (for analytics).
        tenders_using_keyword (list[Tender]): Many-to-many relationship with Tender model, showing all tenders this keyword has matched.
        created_at (datetime): Timestamp of when this keyword record was created.
        updated_at (datetime): Timestamp of last update to this keyword record.
    """

    __tablename__ = "keywords"
    
    # ---------- Columns (Schema) ----------
    id = Column(Integer, primary_key=True, index=True)  # Unique identifier
    keyword = Column(String(100), nullable=False, index=True)  # The keyword value itself
    category = Column(String(50), nullable=False, index=True)  # sector, activity_fit, geography, source_tag
    description = Column(String(500), nullable=True)  # Optional textual description
    
    # ---------- Settings ----------
    is_active = Column(Boolean, default=True, index=True)  # If keyword is enabled
    case_sensitive = Column(Boolean, default=False)  # Case sensitivity for matching
    
    # ---------- Usage Tracking ----------
    usage_count = Column(Integer, default=0)  # How many tenders has this keyword matched?
    last_used = Column(DateTime, nullable=True)  # When was this keyword last matched?
    
    # ---------- Statistics ----------
    match_statistics = Column(Text, nullable=True)  # JSON string with detailed match statistics (optional analytics)
    
    # ---------- Relationships ----------
    # Many-to-many: Which tenders were matched by this keyword?
    tenders_using_keyword = relationship(
        "Tender", 
        secondary="tender_keywords", 
        back_populates="matched_keywords"
    )
    
    # ---------- Metadata ----------
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # Timestamp of creation
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # Timestamp of last modification

    # ---------- Methods ----------
    def __repr__(self):
        """
        String representation for debugging/logging.

        Example:
            <Keyword(id=1, keyword='Ethiopia', category='geography', usage=12)>
        """
        return f"<Keyword(id={self.id}, keyword='{self.keyword}', category='{self.category}', usage={self.usage_count})>"
    
    def increment_usage(self):
        """
        Helper method to increment the usage counter and update last-used timestamp.
        Intended to be called whenever this keyword is matched in a new tender.
        Automatically sets updated_at as well.
        """
        self.usage_count += 1
        self.last_used = datetime.utcnow()
        self.updated_at = datetime.utcnow()

# =======================================================================================
# DETAILED COMMENTS ABOUT THIS CODE AND FILE:
# 
# - Purpose:
#   This file defines the SQLAlchemy ORM model for "Keyword" records, representing
#   user-configurable keywords used to categorize and filter tenders as part of a
#   tender monitoring/tracking application.
# 
# - Structure:
#   - Each Keyword has a string value (`keyword`), belongs to a `category` (such as
#     sector, activity_fit, geography, source_tag), and may have an optional `description`.
#   - The `is_active` flag allows enabling/disabling keywords without deletion.
#   - `case_sensitive` controls whether keyword matching should distinguish case.
# 
# - Usage & Analytics:
#   - `usage_count` and `last_used` provide lightweight analytics, tracking how
#     often and when a keyword is used in matching tenders.
#   - `match_statistics` offers a hook for storing richer statistics/metrics
#     as a JSON-serialized string for deeper analysis or dashboards.
#   - The `increment_usage` helper method encapsulates usage/bookkeeping logic.
# 
# - Relationships:
#   - The `tenders_using_keyword` relationship enables efficient queries for all
#     tenders matched by any given keyword (and vice versa), using a 
#     many-to-many join table ("tender_keywords" association).
# 
# - Metadata:
#   - Creation and last-update timestamps facilitate auditing and display.
# 
# - Best Practices:
#   - Consistent column naming, indexing of key fields (`keyword`, `category`, `is_active`).
#   - ORM representation string and helper methods facilitate maintainable code.
# 
# - Integration:
#   - This model is referenced and accessed throughout the app for any feature
#     involving keyword monitoring, alerting, filtering, or reporting.
#   - Works hand-in-hand with the Tender model and the join table association.
# 
# =======================================================================================