"""
Enhanced Tender Repository with Keyword Tracking
"""
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
import logging

logger = logging.getLogger(__name__)

from app.models.tender import Tender, DetailedTender
from app.models.keyword import Keyword

class TenderRepository:
    """Enhanced repository for tender database operations with keyword tracking"""
    
    def save_tender(self, db: Session, page_id: int, title: str, url: str, 
                   tender_date: Optional[str], category: str, description: str,
                   matched_keywords: List[str] = None, keyword_count: int = 0) -> Optional[Tender]:
        """
        Save a tender with keyword tracking.

        - Parses the input tender_date with robust format fallback.
        - Avoids duplicate tenders by checking by URL.
        - Serializes matched keywords to JSON for storage.
        - Associates tender with matching keywords (for reporting/statistics).
        - Commits changes safely and handles rollback on exceptions.
        """
        try:
            # Parse date if provided, attempt multiple formats if needed.
            parsed_date = None
            if tender_date:
                try:
                    parsed_date = datetime.strptime(tender_date, '%Y-%m-%d')
                except ValueError:
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                        try:
                            parsed_date = datetime.strptime(tender_date, fmt)
                            break
                        except ValueError:
                            continue
            
            # Avoid saving duplicate tenders (by URL).
            existing = db.query(Tender).filter(Tender.url == url).first()
            if existing:
                logger.info(f"Tender already exists: {title[:50]}...")
                return existing
            
            # Create the new Tender object.
            tender = Tender(
                title=title,
                url=url,
                tender_date=parsed_date,
                category=category,
                description=description,
                page_id=page_id,
                matched_keywords_json=json.dumps(matched_keywords or []),
                keyword_count=keyword_count
            )
            
            db.add(tender)
            db.flush()  # Assigns an ID to the new tender.
            
            # Store associations with matching keywords (if any keywords matched).
            if matched_keywords:
                self._save_keyword_associations(db, tender.id, matched_keywords)
            
            db.commit()
            db.refresh(tender)
            
            logger.info(f"Saved tender: {title[:50]}... (Keywords: {keyword_count})")
            return tender
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving tender: {e}")
            raise e
    
    def _save_keyword_associations(self, db: Session, tender_id: int, matched_keywords: List[str]):
        """
        Save tender-keyword associations in the database.

        - Retrieves all active keywords from the database and builds a lowercase map.
        - For each matched keyword string:
            - If found in active keywords, creates a link in the association table using a raw SQL INSERT OR IGNORE (robust for many-to-many).
            - Increments the keyword usage stats.
            - Logs association or missing keyword.
        """
        try:
            all_keywords = db.query(Keyword).filter(Keyword.is_active == True).all()
            keyword_map = {kw.keyword.lower(): kw for kw in all_keywords}
            
            for keyword_str in matched_keywords:
                keyword_lower = keyword_str.lower()
                if keyword_lower in keyword_map:
                    keyword_obj = keyword_map[keyword_lower]
                    
                    # Association creation via SQL.
                    db.execute(text("""
                        INSERT OR IGNORE INTO tender_keywords (tender_id, keyword_id, created_at)
                        VALUES (:tender_id, :keyword_id, :created_at)
                    """), {
                        'tender_id': tender_id,
                        'keyword_id': keyword_obj.id,
                        'created_at': datetime.utcnow()
                    })
                    
                    # Increment stats.
                    keyword_obj.increment_usage()
                    
                    logger.debug(f"Associated tender {tender_id} with keyword '{keyword_str}'")
                else:
                    logger.warning(f"Keyword '{keyword_str}' not found in database")
            
        except Exception as e:
            logger.error(f"Error saving keyword associations: {e}")
    
    def save_detailed_tender(self, db: Session, tender_id: int, detailed_info: Dict[str, Any]) -> Optional[DetailedTender]:
        """
        Save detailed tender information, handling multiple possible data types and enrichment.

        - Checks if a DetailedTender already exists for the given tender_id.
        - Converts possibly mixed data types to appropriate DB storage format for:
            - Title, description, requirements, deadline, contact_info, validation info.
        - Updates main Tender to mark as processed.
        - Handles commit/rollback robustly.
        """
        try:
            existing = db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
            if existing:
                logger.info(f"Updating existing detailed tender for tender_id {tender_id}")
                return self._update_existing_detailed_tender(db, existing, detailed_info)
            
            detailed_title = str(detailed_info.get('detailed_title', '')) if detailed_info.get('detailed_title') else ''
            detailed_description = str(detailed_info.get('detailed_description', '')) if detailed_info.get('detailed_description') else ''
            
            # Handle requirements list/str/None.
            requirements = detailed_info.get('requirements')
            if isinstance(requirements, list):
                requirements_str = '\n'.join([str(req) for req in requirements])
            elif requirements:
                requirements_str = str(requirements)
            else:
                requirements_str = None
            
            deadline = self._parse_deadline(detailed_info.get('deadline'))
            
            contact_info = detailed_info.get('contact_info')
            if isinstance(contact_info, dict):
                contact_info_str = json.dumps(contact_info)
            elif contact_info:
                contact_info_str = str(contact_info)
            else:
                contact_info_str = None
            
            date_validation = detailed_info.get('date_validation')
            if date_validation:
                date_validation_str = json.dumps(date_validation)
            else:
                date_validation_str = None
            
            # Compose the new DetailedTender
            detailed_tender = DetailedTender(
                tender_id=tender_id,
                detailed_title=detailed_title,
                detailed_description=detailed_description,
                requirements=requirements_str,
                deadline=deadline,
                contact_info=contact_info_str,
                additional_details=str(detailed_info.get('additional_details', '')) if detailed_info.get('additional_details') else None,
                full_content=str(detailed_info.get('full_content', '')) if detailed_info.get('full_content') else '',
                processing_status="processed",
                date_validation=date_validation_str,
                processed_at=datetime.utcnow()
            )
            
            # Mark the main tender as processed as well.
            db_tender = db.query(Tender).filter(Tender.id == tender_id).first()
            if db_tender:
                db_tender.is_processed = True
                db_tender.updated_at = datetime.utcnow()
            
            db.add(detailed_tender)
            db.commit()
            db.refresh(detailed_tender)
            
            logger.info(f"Successfully saved detailed info for tender ID: {tender_id}")
            return detailed_tender
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving detailed tender {tender_id}: {str(e)}")
            raise e
    
    def _update_existing_detailed_tender(self, db: Session, existing: DetailedTender, detailed_info: Dict[str, Any]) -> DetailedTender:
        """
        Update an already existing DetailedTender with new info.

        - Only fields present in new detailed_info are updated.
        - Handles lists/dicts for requirements/contact info similarly to the create method.
        - Sets updated/processed timestamps and status.
        - Commits the change.
        """
        try:
            if detailed_info.get('detailed_title'):
                existing.detailed_title = str(detailed_info['detailed_title'])
            if detailed_info.get('detailed_description'):
                existing.detailed_description = str(detailed_info['detailed_description'])
            
            # Requirements update
            if detailed_info.get('requirements'):
                requirements = detailed_info['requirements']
                if isinstance(requirements, list):
                    existing.requirements = '\n'.join([str(req) for req in requirements])
                else:
                    existing.requirements = str(requirements)
            
            # Contact info update
            if detailed_info.get('contact_info'):
                contact_info = detailed_info['contact_info']
                if isinstance(contact_info, dict):
                    existing.contact_info = json.dumps(contact_info)
                else:
                    existing.contact_info = str(contact_info)
            
            if detailed_info.get('additional_details'):
                existing.additional_details = str(detailed_info['additional_details'])
            if detailed_info.get('full_content'):
                existing.full_content = str(detailed_info['full_content'])
            
            # Deadline/date validation
            if detailed_info.get('deadline'):
                existing.deadline = self._parse_deadline(detailed_info['deadline'])
            
            if detailed_info.get('date_validation'):
                existing.date_validation = json.dumps(detailed_info['date_validation'])
            
            existing.updated_at = datetime.utcnow()
            existing.processed_at = datetime.utcnow()
            existing.processing_status = "processed"
            
            db.commit()
            return existing
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating detailed tender: {e}")
            raise e
    
    def _parse_deadline(self, deadline_value) -> Optional[datetime]:
        """
        Parse a deadline value (str, datetime or None) to a datetime object.

        - Tries multiple string date formats.
        - Returns None if parsing fails or value isn't set.
        """
        if not deadline_value:
            return None
        
        try:
            if isinstance(deadline_value, datetime):
                return deadline_value
            
            deadline_str = str(deadline_value)
            for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%d.%m.%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(deadline_str, fmt)
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse deadline: {deadline_value}")
            return None
            
        except Exception as e:
            logger.warning(f"Deadline parsing error: {e}")
            return None
    
    def get_unnotified_tenders(self, db: Session, category: str) -> List[Tender]:
        """
        Returns all non-notified tenders for a given category.

        - If category is 'esg' or 'credit_rating', also returns those marked 'both'.
        - Otherwise, strictly matches category.
        """
        query = db.query(Tender).filter(
            and_(
                Tender.is_notified == False,
                or_(
                    Tender.category == category,
                    Tender.category == "both" if category in ["esg", "credit_rating"] else False
                )
            )
        )
        return query.all()
    
    def get_tenders_with_keywords(self, db: Session, keywords: List[str], limit: int = 100) -> List[Tender]:
        """
        Returns up to limit tenders where any matched_keywords_json entry matches one of the provided keywords.
        (Case insensitive, slow for large numbers but keeps SQLite compatibility.)

        - Doubles the query limit for filtering, then only returns the first 'limit' matches.
        - Safe JSON loads with error skip.
        """
        tenders = []
        for tender in db.query(Tender).limit(limit * 2).all():
            if tender.matched_keywords_json:
                try:
                    tender_keywords = json.loads(tender.matched_keywords_json)
                    if any(kw.lower() in [tk.lower() for tk in tender_keywords] for kw in keywords):
                        tenders.append(tender)
                        if len(tenders) >= limit:
                            break
                except json.JSONDecodeError:
                    continue
        
        return tenders
    
    def get_keyword_usage_stats(self, db: Session) -> Dict[str, Any]:
        """
        Returns usage statistics for keywords.

        - Tallies up keyword usage, splits by category.
        - Returns top 10 keywords by usage (with last used time).
        - Used for reports/monitoring keyword relevance.
        """
        try:
            keywords_with_usage = db.query(Keyword).filter(Keyword.usage_count > 0).all()
            
            stats = {
                'total_keywords_used': len(keywords_with_usage),
                'top_keywords': [],
                'category_breakdown': {'esg': 0, 'credit_rating': 0},
                'total_keyword_matches': sum(kw.usage_count for kw in keywords_with_usage)
            }
            
            sorted_keywords = sorted(keywords_with_usage, key=lambda x: x.usage_count, reverse=True)
            stats['top_keywords'] = [
                {
                    'keyword': kw.keyword,
                    'category': kw.category,
                    'usage_count': kw.usage_count,
                    'last_used': kw.last_used.isoformat() if kw.last_used else None
                }
                for kw in sorted_keywords[:10]
            ]
            
            # Build per-category breakdown
            for kw in keywords_with_usage:
                if kw.category in stats['category_breakdown']:
                    stats['category_breakdown'][kw.category] += kw.usage_count
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting keyword usage stats: {e}")
            return {}
    
    def mark_tender_notified(self, db: Session, tender_id: int):
        """
        Mark a tender as having been notified to a user/subscriber.

        - Sets is_notified = True and updates the timestamp.
        """
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if tender:
            tender.is_notified = True
            tender.updated_at = datetime.utcnow()
            db.commit()
    
    def get_tenders_by_page(self, db: Session, page_id: int, limit: int = 50) -> List[Tender]:
        """
        Get most recent tenders for a specific source/page, descending by creation.
        """
        return db.query(Tender).filter(Tender.page_id == page_id).order_by(Tender.created_at.desc()).limit(limit).all()
    
    def get_recent_tenders(self, db: Session, days: int = 7, limit: int = 100) -> List[Tender]:
        """
        Get tenders added within the last N days, up to a limit.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return db.query(Tender).filter(Tender.created_at >= cutoff_date).order_by(Tender.created_at.desc()).limit(limit).all()
    
    def get_tender_by_id(self, db: Session, tender_id: int) -> Optional[Tender]:
        """
        Get a tender by its unique database ID.
        """
        return db.query(Tender).filter(Tender.id == tender_id).first()
    
    def get_detailed_tender_by_tender_id(self, db: Session, tender_id: int) -> Optional[DetailedTender]:
        """
        Get a detailed tender record (if any exists) for the given tender_id.
        """
        return db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
    
    def check_duplicate_tender(self, db: Session, title: str, url: str, page_id: int) -> bool:
        """
        Check for duplicates for a given tender (by URL primarily, then by title and page).

        - Returns True if a duplicate (by URL or by title/page) exists, False otherwise.
        """
        # Try URL duplicate
        existing_by_url = db.query(Tender).filter(
            and_(
                Tender.url == url,
                Tender.page_id == page_id
            )
        ).first()
        
        if existing_by_url:
            return True
        
        # Try exact title duplicate for that page
        existing_by_title = db.query(Tender).filter(
            and_(
                Tender.title == title,
                Tender.page_id == page_id
            )
        ).first()
        
        return existing_by_title is not None

# ------------------------------------------------------------------------------------------
# FILE COMMENTS:
#
# File: app/repositories/tender_repository.py
# 
# This file defines the core persistence/repository logic for dealing with tender (procurement/invitation) records
# in the application's database. It uses SQLAlchemy ORM for all its database interactions and also works with
# two primary data models: Tender (basic tender info) and DetailedTender (richer, parsed info per tender). It also
# leverages the Keyword model for keyword tracking and statistics.
#
# Main Capabilities:
# - Inserting new tenders and associating them with detected keywords, tracking keyword usage.
# - Saving and updating detailed parsed tender information, flexibly converting source data into stable database formats.
# - Avoiding duplicates via checks on URLs and titles per source ('page').
# - Marking tenders as notified to users/subscribers.
# - Retrieving tenders by a variety of filters: by recency, by page, by keyword, or to support notifications.
# - Collecting statistics on keyword usage and tender keyword matches, enabling monitoring and reporting.
# - Uses robust error handling, rollback on failure, and logs all major actions and issues.
# 
# Notable Implementation Details:
# - Keyword associations are managed with direct SQL for reliability in many-to-many junctions.
# - Dates are parsed flexibly from strings with various possible formats.
# - Some database fields (matched_keywords_json, contact_info, etc.) use JSON serialization for structure.
# - Designed for extendibility, as seen in helper methods and conventions.
#
# This is a core backend file supporting tender aggregation, notification, and keyword analytics services.