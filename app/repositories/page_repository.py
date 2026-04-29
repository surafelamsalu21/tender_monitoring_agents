"""
Page Repository
Database operations for monitored page management
"""  # File docstring: Describes purpose as page repository and DB ops for monitored page mgmt

from datetime import datetime    # Import datetime for timestamping DB records
from typing import List, Optional  # Import typing for type hints
from sqlalchemy.orm import Session  # Import Session for SQLAlchemy DB access

from app.models.page import MonitoredPage  # Import MonitoredPage model for ORM queries

class PageRepository:  # Repository pattern encapsulating all DB ops on MonitoredPages
    """Repository for monitored page database operations"""  # Docstring specifying intent and scope
    
    def get_active_pages(self, db: Session) -> List[MonitoredPage]:  # Gets all pages marked as active from DB
        """Get all active monitored pages"""  # Docstring for method
        return db.query(MonitoredPage).filter(MonitoredPage.is_active == True).all()  # Query active pages using SQLAlchemy
    
    def get_all_pages(self, db: Session) -> List[MonitoredPage]:  # Returns all monitored page records
        """Get all monitored pages"""  # Docstring for method
        return db.query(MonitoredPage).all()  # DB call to fetch all monitored pages
    
    def get_page_by_id(self, db: Session, page_id: int) -> Optional[MonitoredPage]:  # Find monitored page by PK id
        """Get page by ID"""  # Docstring for method
        return db.query(MonitoredPage).filter(MonitoredPage.id == page_id).first()  # Filter by id and get first result; None if not found
    
    def get_page_by_url(self, db: Session, url: str) -> Optional[MonitoredPage]:  # Find monitored page by its URL
        """Get page by URL"""  # Docstring for method
        return db.query(MonitoredPage).filter(MonitoredPage.url == url).first()  # Filter by URL, get single or None
    
    def create_page(self, db: Session, name: str, url: str, description: str = None, 
                   crawl_frequency_hours: int = 3) -> MonitoredPage:  # Create MonitoredPage and store to DB
        """Create a new monitored page"""  # Docstring for creation op
        page = MonitoredPage(
            name=name,  # Set name
            url=url,  # Set url
            description=description,  # Set optional description
            crawl_frequency_hours=crawl_frequency_hours  # Set crawl interval in hours (default: 3)
        )   # Instantiate ORM model
        db.add(page)  # Add to DB session
        db.commit()  # Commit (save) to DB
        db.refresh(page)  # Refresh to get new PK/id and state from DB
        return page  # Return the just-created object
    
    def update_page(self, db: Session, page_id: int, **kwargs) -> Optional[MonitoredPage]:  # Update MonitoredPage fields by id
        """Update a monitored page"""  # Docstring for method
        page = self.get_page_by_id(db, page_id)  # Lookup page first
        if not page:
            return None  # Return None if not found
        
        for key, value in kwargs.items():  # Iterate over provided attributes
            if hasattr(page, key):  # Only update attributes that exist
                setattr(page, key, value)  # Set new value
        
        page.updated_at = datetime.utcnow()  # Update 'updated_at' timestamp
        db.commit()  # Save changes
        db.refresh(page)  # Get updated info
        return page  # Return updated object
    
    def delete_page(self, db: Session, page_id: int) -> bool:  # Delete the page by id
        """Delete a monitored page"""  # Docstring for method
        page = self.get_page_by_id(db, page_id)  # Lookup object
        if not page:
            return False  # Indicate not found
        
        db.delete(page)  # Remove from DB session
        db.commit()  # Save changes
        return True  # Indicate delete success
    
    def update_crawl_status(self, db: Session, page_id: int, success: bool):  # Update crawl results for a page after crawl attempt
        """Update page crawl status"""  # Docstring for method
        page = self.get_page_by_id(db, page_id)  # Fetch object by id
        if not page:
            return  # Silently fail if not found
        
        page.last_crawled = datetime.utcnow()  # Set last crawled time
        
        if success:  # If crawl succeeded
            page.consecutive_failures = 0  # Reset failure counter
            page.last_successful_crawl = datetime.utcnow()  # Set successful crawl time
        else:
            page.consecutive_failures += 1  # Increment failure counter
        
        db.commit()  # Persist status update

# ----------------------------------------
# FILE NOTES:
# - This file implements the PageRepository class, encapsulating CRUD and utility operations
#   relating to "MonitoredPage" objects in the database.
# - It uses SQLAlchemy ORM models and sessions to perform standard queries, record creation,
#   field updates, soft/hard deletes, and crawl-status tracking on page records.
# - Responsibilities include: separation of data logic from business logic, enabling
#   reusability and easy mocking for unit testing.
# - Typical usage: injected or instantiated by a service, resource, or API layer,
#   then used to manage monitored pages for scraping/crawling.
# - All major DB-write operations use commit/refresh to keep returned Python objects up to date.
# - Defensive None/False returns in cases of record non-existence help prevent upstream errors.
