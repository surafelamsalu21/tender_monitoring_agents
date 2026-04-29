"""
Monitored Pages API Routes
CRUD operations for monitored pages
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl

from app.core.database import get_db
from app.repositories.page_repository import PageRepository
from app.models.page import MonitoredPage

router = APIRouter()

class PageCreate(BaseModel):
    name: str
    url: HttpUrl
    description: Optional[str] = None
    crawl_frequency_hours: int = 3

class PageUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    description: Optional[str] = None
    crawl_frequency_hours: Optional[int] = None
    is_active: Optional[bool] = None

@router.get("/", response_model=List[dict])
async def get_pages(db: Session = Depends(get_db)):
    """Get all monitored pages"""
    page_repo = PageRepository()
    pages = page_repo.get_all_pages(db)
    
    return [
        {
            "id": page.id,
            "name": page.name,
            "url": str(page.url),
            "description": page.description,
            "is_active": page.is_active,
            "crawl_frequency_hours": page.crawl_frequency_hours,
            "last_crawled": page.last_crawled.isoformat() if page.last_crawled else None,
            "last_successful_crawl": page.last_successful_crawl.isoformat() if page.last_successful_crawl else None,
            "consecutive_failures": page.consecutive_failures,
            "status": page.status,
            "is_healthy": page.is_healthy,
            "created_at": page.created_at.isoformat(),
            "tender_count": len(page.tenders) if page.tenders else 0
        }
        for page in pages
    ]

@router.get("/{page_id}")
async def get_page(page_id: int, db: Session = Depends(get_db)):
    """Get a specific monitored page"""
    page_repo = PageRepository()
    page = page_repo.get_page_by_id(db, page_id)
    
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    return {
        "id": page.id,
        "name": page.name,
        "url": str(page.url),
        "description": page.description,
        "is_active": page.is_active,
        "crawl_frequency_hours": page.crawl_frequency_hours,
        "last_crawled": page.last_crawled.isoformat() if page.last_crawled else None,
        "last_successful_crawl": page.last_successful_crawl.isoformat() if page.last_successful_crawl else None,
        "consecutive_failures": page.consecutive_failures,
        "status": page.status,
        "is_healthy": page.is_healthy,
        "created_at": page.created_at.isoformat(),
        "updated_at": page.updated_at.isoformat(),
        "tenders": [
            {
                "id": tender.id,
                "title": tender.title,
                "category": tender.category,
                "created_at": tender.created_at.isoformat()
            }
            for tender in page.tenders[-10:]  # Last 10 tenders
        ] if page.tenders else []
    }

@router.post("/", response_model=dict)
async def create_page(page_data: PageCreate, db: Session = Depends(get_db)):
    """Create a new monitored page"""
    page_repo = PageRepository()
    
    # Check if URL already exists
    existing = page_repo.get_page_by_url(db, str(page_data.url))
    if existing:
        raise HTTPException(status_code=400, detail="URL already exists")
    
    page = page_repo.create_page(
        db,
        name=page_data.name,
        url=str(page_data.url),
        description=page_data.description,
        crawl_frequency_hours=page_data.crawl_frequency_hours
    )
    
    return {
        "id": page.id,
        "name": page.name,
        "url": page.url,
        "message": "Page created successfully"
    }

@router.put("/{page_id}")
async def update_page(page_id: int, page_data: PageUpdate, db: Session = Depends(get_db)):
    """Update a monitored page"""
    page_repo = PageRepository()
    
    # Convert URL to string if provided
    update_data = page_data.dict(exclude_unset=True)
    if 'url' in update_data:
        update_data['url'] = str(update_data['url'])
    
    page = page_repo.update_page(db, page_id, **update_data)
    
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    return {
        "id": page.id,
        "name": page.name,
        "url": page.url,
        "message": "Page updated successfully"
    }

@router.delete("/{page_id}")
async def delete_page(page_id: int, db: Session = Depends(get_db)):
    """Delete a monitored page"""
    page_repo = PageRepository()
    
    success = page_repo.delete_page(db, page_id)
    if not success:
        raise HTTPException(status_code=404, detail="Page not found")
    
    return {"message": "Page deleted successfully"}

@router.get("/{page_id}/tenders")
async def get_page_tenders(page_id: int, limit: int = 50, db: Session = Depends(get_db)):
    """Get tenders for a specific page"""
    from app.repositories.tender_repository import TenderRepository
    
    page_repo = PageRepository()
    tender_repo = TenderRepository()
    
    # Check if page exists
    page = page_repo.get_page_by_id(db, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    tenders = tender_repo.get_tenders_by_page(db, page_id, limit)
    
    return [
        {
            "id": tender.id,
            "title": tender.title,
            "url": tender.url,
            "category": tender.category,
            "tender_date": tender.tender_date.isoformat() if tender.tender_date else None,
            "created_at": tender.created_at.isoformat(),
            "is_notified": tender.is_notified
        }
        for tender in tenders
    ]
