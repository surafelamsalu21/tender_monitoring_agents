from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import Config

Base = declarative_base()

class MonitoredPage(Base):
    __tablename__ = "monitored_pages"
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    last_crawled = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    tenders = relationship("Tender", back_populates="page")

class Keyword(Base):
    __tablename__ = "keywords"
    
    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, index=True)
    category = Column(String)  # 'esg' or 'credit_rating'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Tender(Base):
    __tablename__ = "tenders"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    tender_date = Column(DateTime)
    category = Column(String)  # 'esg', 'credit_rating', or 'both'
    description = Column(Text)
    full_content = Column(Text)
    is_processed = Column(Boolean, default=False)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    page_id = Column(Integer, ForeignKey("monitored_pages.id"))
    
    # Relationships
    page = relationship("MonitoredPage", back_populates="tenders")
    detailed_tender = relationship("DetailedTender", back_populates="tender")

class DetailedTender(Base):
    __tablename__ = "detailed_tenders"
    
    id = Column(Integer, primary_key=True, index=True)
    tender_id = Column(Integer, ForeignKey("tenders.id"))
    full_title = Column(Text)
    comprehensive_description = Column(Text)
    requirements = Column(Text)
    deadline = Column(DateTime)
    contact_info = Column(Text)
    additional_details = Column(Text)
    full_content = Column(Text)  # Complete scraped content
    processing_status = Column(String, default='processed')  # 'processed', 'failed'
    processed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    tender = relationship("Tender", back_populates="detailed_tender")

class CrawlLog(Base):
    __tablename__ = "crawl_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    page_id = Column(Integer, ForeignKey("monitored_pages.id"))
    status = Column(String)  # 'success', 'failed'
    tenders_found = Column(Integer, default=0)
    error_message = Column(Text)
    crawl_time = Column(DateTime, default=datetime.utcnow)

# Database setup
engine = create_engine(Config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
