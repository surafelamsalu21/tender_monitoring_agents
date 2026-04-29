"""
Keyword Repository
Database operations for keyword management
"""
from typing import List, Optional  # Import List and Optional for type annotations
from sqlalchemy.orm import Session  # Import Session to perform DB operations using SQLAlchemy

from app.models.keyword import Keyword  # Import the Keyword ORM model to access the keyword table

class KeywordRepository:
    """Repository for keyword database operations"""
    
    def get_keywords_by_category(self, db: Session, category: str) -> List[str]:
        """
        Get all active keywords belonging to a specific category.
        
        Args:
            db (Session): SQLAlchemy session object for DB access.
            category (str): category to filter keywords by.
        
        Returns:
            List[str]: List of keyword strings that are active and belong to the specified category.
        """
        keywords = db.query(Keyword).filter(
            Keyword.category == category,
            Keyword.is_active == True
        ).all()  # Query all keywords in the given category that are active
        return [k.keyword for k in keywords]  # Return only the 'keyword' strings
    
    def get_all_keywords(self, db: Session) -> List[Keyword]:
        """
        Retrieve all keyword records from the database.
        
        Args:
            db (Session): SQLAlchemy session object.
        
        Returns:
            List[Keyword]: List of all Keyword ORM objects.
        """
        return db.query(Keyword).all()
    
    def get_keyword_by_id(self, db: Session, keyword_id: int) -> Optional[Keyword]:
        """
        Retrieve a specific keyword by its primary key ID.
        
        Args:
            db (Session): SQLAlchemy session object.
            keyword_id (int): Primary key ID of the keyword.
        
        Returns:
            Optional[Keyword]: The Keyword object if found, otherwise None.
        """
        return db.query(Keyword).filter(Keyword.id == keyword_id).first()
    
    def create_keyword(self, db: Session, keyword: str, category: str, 
                      description: str = None, case_sensitive: bool = False) -> Keyword:
        """
        Create and persist a new keyword record in the database.
        
        Args:
            db (Session): SQLAlchemy session object.
            keyword (str): The keyword string to insert.
            category (str): The category for the keyword.
            description (str, optional): Descriptive text about the keyword.
            case_sensitive (bool, optional): If the keyword should be matched case-sensitively (default False).
        
        Returns:
            Keyword: The newly created keyword ORM object.
        """
        new_keyword = Keyword(
            keyword=keyword,
            category=category,
            description=description,
            case_sensitive=case_sensitive
        )
        db.add(new_keyword)  # Add to current DB session
        db.commit()  # Commit transaction (flushes and persists changes)
        db.refresh(new_keyword)  # Refresh ORM instance with DB values (e.g., get the assigned primary key)
        return new_keyword
    
    def update_keyword(self, db: Session, keyword_id: int, **kwargs) -> Optional[Keyword]:
        """
        Update fields of an existing keyword.
        
        Args:
            db (Session): SQLAlchemy session object.
            keyword_id (int): Primary key ID of the keyword to update.
            **kwargs: Arbitrary keyword arguments corresponding to fields to update.
        
        Returns:
            Optional[Keyword]: The updated Keyword object, or None if not found.
        """
        keyword = self.get_keyword_by_id(db, keyword_id)
        if not keyword:
            return None  # If keyword does not exist, return None
        
        for key, value in kwargs.items():
            if hasattr(keyword, key):  # Only update attributes that are valid for this ORM model
                setattr(keyword, key, value)
        
        db.commit()  # Commit the transaction to persist changes
        db.refresh(keyword)  # Refresh instance to get updated values
        return keyword
    
    def delete_keyword(self, db: Session, keyword_id: int) -> bool:
        """
        Delete a keyword record by its ID.
        
        Args:
            db (Session): SQLAlchemy session object.
            keyword_id (int): Primary key ID of the keyword to delete.
        
        Returns:
            bool: True if delete is successful, False if keyword was not found.
        """
        keyword = self.get_keyword_by_id(db, keyword_id)
        if not keyword:
            return False  # Indicates not found
        
        db.delete(keyword)  # Remove object from DB session
        db.commit()  # Commit to persist delete
        return True


# -----------------------------------------
# Detailed Comments & File Overview
# -----------------------------------------

# File purpose:
#   This file implements the 'KeywordRepository' class which encapsulates all database operations
#   related to the 'Keyword' ORM model (which represents the keywords table in the database).
#   Using the repository pattern, it centralizes all logic for CRUD (Create, Read, Update, Delete)
#   operations for keywords, abstracting SQLAlchemy details away from the rest of the app.

# Code breakdown:
#   - get_keywords_by_category:
#       Retrieves all keyword strings that match a given category and are marked as active.
#       Useful for searching/filtering by user-defined groupings.
#   - get_all_keywords:
#       Returns all Keyword ORM objects in the DB, regardless of category or active status.
#   - get_keyword_by_id:
#       Fetches a specific keyword (ORM object) by its database primary key.
#   - create_keyword:
#       Adds a new keyword record to the database, supporting optional description & case sensitivity.
#       Commits the record and returns the ORM object with assigned ID.
#   - update_keyword:
#       Updates all attributes (fields) present in kwargs if the keyword exists.
#       Only updates keyword fields that are valid for the ORM model.
#   - delete_keyword:
#       Deletes a keyword from the database by ID, returning True on success, False if not found.

# Design notes:
#   - Uses SQLAlchemy ORM and the repository pattern for clean separation of DB logic.
#   - Adds type hints and docstrings for clarity.
#   - Ensures commit/refresh after each change for DB consistency.
#   - Handles keyword existence checks gracefully (returns None or False if not found).

# Usage:
#   This repository is intended to be used by the application's services, endpoints, or other layers
#   that need to interact with the keyword data while keeping DB logic centralized and reusable.
   