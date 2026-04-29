from sqlalchemy.orm import Session
from models import MonitoredPage, Keyword, Tender, CrawlLog, DetailedTender, get_db, create_tables
from typing import List, Optional, Dict
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        create_tables()
    
    def add_monitored_page(self, db: Session, url: str, name: str) -> MonitoredPage:
        """Add a new page to monitor"""
        existing = db.query(MonitoredPage).filter(MonitoredPage.url == url).first()
        if existing:
            return existing
        
        page = MonitoredPage(url=url, name=name)
        db.add(page)
        db.commit()
        db.refresh(page)
        logger.info(f"Added monitored page: {name} ({url})")
        return page
    
    def get_active_pages(self, db: Session) -> List[MonitoredPage]:
        """Get all active monitored pages"""
        return db.query(MonitoredPage).filter(MonitoredPage.is_active == True).all()
    
    def add_keywords(self, db: Session, keywords: List[str], category: str):
        """Add keywords for a category"""
        for keyword_text in keywords:
            existing = db.query(Keyword).filter(
                Keyword.keyword == keyword_text,
                Keyword.category == category
            ).first()
            
            if not existing:
                keyword = Keyword(keyword=keyword_text, category=category)
                db.add(keyword)
        
        db.commit()
        logger.info(f"Added {len(keywords)} keywords for category: {category}")
    
    def get_keywords_by_category(self, db: Session, category: str) -> List[str]:
        """Get active keywords for a category"""
        keywords = db.query(Keyword).filter(
            Keyword.category == category,
            Keyword.is_active == True
        ).all()
        return [k.keyword for k in keywords]
    
    def save_tender(self, db: Session, page_id: int, title: str, url: str, date: str, category: str, description: str) -> Tender:
        """Save or update a tender"""
        existing = db.query(Tender).filter(Tender.url == url).first()
        
        if existing:
            # Update existing tender
            existing.title = title
            existing.description = description
            existing.category = category
            existing.is_processed = True
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # Create new tender
            tender_date = None
            if date and date != 'null':
                try:
                    tender_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                except:
                    try:
                        tender_date = datetime.strptime(date, '%Y-%m-%d')
                    except:
                        pass
            
            tender = Tender(
                title=title,
                url=url,
                tender_date=tender_date,
                category=category,
                description=description,
                page_id=page_id,
                is_processed=True
            )
            
            db.add(tender)
            db.commit()
            db.refresh(tender)
            logger.info(f"Saved new tender: {tender.title}")
            return tender
    
    def get_unnotified_tenders(self, db: Session, category: Optional[str] = None) -> List[Tender]:
        """Get tenders that haven't been notified yet"""
        query = db.query(Tender).filter(
            Tender.is_notified == False,
            Tender.is_processed == True
        )
        
        if category:
            query = query.filter(Tender.category.in_([category, 'both']))
        
        return query.all()
    
    def mark_tender_notified(self, db: Session, tender_id: int):
        """Mark a tender as notified"""
        tender = db.query(Tender).filter(Tender.id == tender_id).first()
        if tender:
            tender.is_notified = True
            db.commit()
    
    def log_crawl(self, db: Session, page_id: int, status: str, tenders_found: int = 0, error_message: str = None):
        """Log crawl activity"""
        log = CrawlLog(
            page_id=page_id,
            status=status,
            tenders_found=tenders_found,
            error_message=error_message
        )
        db.add(log)
        db.commit()
    
    def get_recent_tenders(self, db: Session, days: int = 7) -> List[Tender]:
        """Get tenders from the last N days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return db.query(Tender).filter(
            Tender.created_at >= cutoff_date
        ).order_by(Tender.created_at.desc()).all()
    
    def save_detailed_tender(self, db: Session, tender_id: int, detailed_info: Dict):
        """Save detailed tender information"""
        try:
            # Check if detailed tender already exists
            existing = db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
            if existing:
                logger.info(f"Detailed tender already exists for tender_id {tender_id}, updating...")
                existing.full_title = detailed_info.get('title')
                existing.comprehensive_description = detailed_info.get('description')
                existing.requirements = detailed_info.get('requirements')
                existing.contact_info = detailed_info.get('contact_info')
                existing.additional_details = detailed_info.get('additional_details')
                existing.full_content = detailed_info.get('full_content')
                existing.processed_at = datetime.utcnow()
                db.commit()
                return existing
            
            # Parse deadline if provided
            deadline = None
            if detailed_info.get('deadline'):
                try:
                    deadline = datetime.fromisoformat(detailed_info['deadline'].replace('Z', '+00:00'))
                except:
                    try:
                        deadline = datetime.strptime(detailed_info['deadline'], '%Y-%m-%d')
                    except:
                        pass
            
            detailed_tender = DetailedTender(
                tender_id=tender_id,
                full_title=detailed_info.get('title'),
                comprehensive_description=detailed_info.get('description'),
                requirements=detailed_info.get('requirements'),
                deadline=deadline,
                contact_info=detailed_info.get('contact_info'),
                additional_details=detailed_info.get('additional_details'),
                full_content=detailed_info.get('full_content'),
                processing_status='processed'
            )
            
            db.add(detailed_tender)
            db.commit()
            logger.info(f"Saved detailed tender for tender_id {tender_id}")
            return detailed_tender
            
        except Exception as e:
            logger.error(f"Error saving detailed tender: {e}")
            db.rollback()
            return None
    
    def get_detailed_tender(self, db: Session, tender_id: int) -> Optional[DetailedTender]:
        """Get detailed tender by tender_id"""
        return db.query(DetailedTender).filter(DetailedTender.tender_id == tender_id).first()
    
    def get_tenders_without_details(self, db: Session, limit: int = 10) -> List[Tender]:
        """Get tenders that don't have detailed information yet"""
        return db.query(Tender).outerjoin(DetailedTender).filter(
            DetailedTender.id.is_(None)
        ).limit(limit).all()

    def initialize_default_data(self):
        """Initialize database with default pages and keywords"""
        from config import Config
        
        with next(get_db()) as db:
            # Add default monitored page
            self.add_monitored_page(
                db, 
                "https://corp.uzairways.com/ru/press-center/tenders",
                "Uzbekistan Airways Tenders"
            )
            
            # Add default keywords
            self.add_keywords(db, Config.ESG_KEYWORDS, "esg")
            self.add_keywords(db, Config.CREDIT_RATING_KEYWORDS, "credit_rating")
            
            logger.info("Database initialized with default data")

def test_database():
    """Test database operations"""
    db_manager = DatabaseManager()
    db_manager.initialize_default_data()
    
    with next(get_db()) as db:
        # Test getting pages
        pages = db_manager.get_active_pages(db)
        print(f"✓ Found {len(pages)} active pages")
        
        # Test getting keywords
        esg_keywords = db_manager.get_keywords_by_category(db, "esg")
        credit_keywords = db_manager.get_keywords_by_category(db, "credit_rating")
        print(f"✓ ESG keywords: {len(esg_keywords)}")
        print(f"✓ Credit rating keywords: {len(credit_keywords)}")

if __name__ == "__main__":
    test_database()
    print("database.py run finished")
    print("second test line for diff review")
