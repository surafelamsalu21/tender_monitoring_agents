"""
Tender API Routes
CRUD operations for tenders
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from app.core.database import get_db
from app.repositories.tender_repository import TenderRepository
from app.models.tender import Tender, DetailedTender

router = APIRouter()

@router.get("/", response_model=List[dict])
async def get_tenders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: Optional[str] = Query(None, regex="^(esg|credit_rating|both)$"),
    days: Optional[int] = Query(None, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get tenders with optional filtering"""
    tender_repo = TenderRepository()
    
    if days:
        # Get recent tenders
        tenders = tender_repo.get_recent_tenders(db, days=days, limit=limit)
    else:
        # Get all tenders (simplified query for now)
        tenders = db.query(Tender).offset(skip).limit(limit).all()
    
    # Filter by category if specified
    if category:
        tenders = [t for t in tenders if t.category == category or t.category == "both"]
    
    return [
        {
            "id": tender.id,
            "title": tender.title,
            "url": tender.url,
            "tender_date": tender.tender_date.isoformat() if tender.tender_date else None,
            "category": tender.category,
            "description": tender.description,
            "is_processed": tender.is_processed,
            "is_notified": tender.is_notified,
            "created_at": tender.created_at.isoformat(),
            "page_name": tender.page.name if tender.page else None
        }
        for tender in tenders
    ]

@router.get("/{tender_id}")
async def get_tender(tender_id: int, db: Session = Depends(get_db)):
    """Get a specific tender with detailed information"""
    tender_repo = TenderRepository()
    
    tender = tender_repo.get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    
    # Get detailed information if available
    detailed_tender = tender_repo.get_detailed_tender_by_tender_id(db, tender_id)
    
    result = {
        "id": tender.id,
        "title": tender.title,
        "url": tender.url,
        "tender_date": tender.tender_date.isoformat() if tender.tender_date else None,
        "category": tender.category,
        "description": tender.description,
        "is_processed": tender.is_processed,
        "is_notified": tender.is_notified,
        "created_at": tender.created_at.isoformat(),
        "updated_at": tender.updated_at.isoformat(),
        "page": {
            "id": tender.page.id,
            "name": tender.page.name,
            "url": tender.page.url
        } if tender.page else None
    }
    
    if detailed_tender:
        result["detailed_info"] = {
            "detailed_title": detailed_tender.detailed_title,
            "detailed_description": detailed_tender.detailed_description,
            "requirements": detailed_tender.requirements,
            "deadline": detailed_tender.deadline.isoformat() if detailed_tender.deadline else None,
            "contact_info": detailed_tender.contact_info,
            "additional_details": detailed_tender.additional_details,
            "processing_status": detailed_tender.processing_status,
            "processed_at": detailed_tender.processed_at.isoformat() if detailed_tender.processed_at else None
        }
    
    return result

@router.get("/stats/summary")
async def get_tender_stats(db: Session = Depends(get_db)):
    """Get tender statistics"""
    total_tenders = db.query(Tender).count()
    esg_tenders = db.query(Tender).filter(Tender.category.in_(["esg", "both"])).count()
    credit_tenders = db.query(Tender).filter(Tender.category.in_(["credit_rating", "both"])).count()
    
    # Recent tenders (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_tenders = db.query(Tender).filter(Tender.created_at >= week_ago).count()
    
    # Unnotified tenders
    unnotified = db.query(Tender).filter(Tender.is_notified == False).count()
    
    return {
        "total_tenders": total_tenders,
        "esg_tenders": esg_tenders,
        "credit_rating_tenders": credit_tenders,
        "recent_tenders_7_days": recent_tenders,
        "unnotified_tenders": unnotified,
        "last_updated": datetime.utcnow().isoformat()
    }
