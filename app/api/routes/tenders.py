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
    passes_filter: Optional[bool] = Query(None),
    source: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    opportunity_type: Optional[str] = Query(None),
    min_yes_count: Optional[int] = Query(None, ge=0, le=5),
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
    
    # Apply checklist-based filters
    if passes_filter is not None:
        tenders = [t for t in tenders if bool(t.passes_screening) == passes_filter]
    if source:
        tenders = [t for t in tenders if t.source and source.lower() in t.source.lower()]
    if country:
        tenders = [t for t in tenders if t.country and country.lower() in t.country.lower()]
    if opportunity_type:
        tenders = [
            t for t in tenders
            if t.opportunity_type and opportunity_type.lower() == t.opportunity_type.lower()
        ]
    if min_yes_count is not None:
        tenders = [t for t in tenders if (t.screening_yes_count or 0) >= min_yes_count]
    
    return [
        {
            "id": tender.id,
            "title": tender.title,
            "url": tender.url,
            "opportunity_fingerprint": tender.opportunity_fingerprint,
            "tender_date": tender.tender_date.isoformat() if tender.tender_date else None,
            "description": tender.description,
            "source": tender.source,
            "country": tender.country,
            "opportunity_type": tender.opportunity_type,
            "estimated_budget": tender.estimated_budget,
            "screening_version": tender.screening_version,
            "screening_yes_count": tender.screening_yes_count,
            "passes_screening": tender.passes_screening,
            "screening_step1": tender.screening_step1,
            "screening_step2": tender.screening_step2,
            "screening_step3": tender.screening_step3,
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
        "opportunity_fingerprint": tender.opportunity_fingerprint,
        "tender_date": tender.tender_date.isoformat() if tender.tender_date else None,
        "description": tender.description,
        "source": tender.source,
        "country": tender.country,
        "opportunity_type": tender.opportunity_type,
        "estimated_budget": tender.estimated_budget,
        "screening_version": tender.screening_version,
        "screening_yes_count": tender.screening_yes_count,
        "passes_screening": tender.passes_screening,
        "screening_step1": tender.screening_step1,
        "screening_step2": tender.screening_step2,
        "screening_step3": tender.screening_step3,
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
            "tender_value": detailed_tender.tender_value,
            "duration": detailed_tender.duration,
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
    passed_screening = db.query(Tender).filter(Tender.passes_screening == True).count()
    failed_screening = db.query(Tender).filter(Tender.passes_screening == False).count()
    
    # Recent tenders (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_tenders = db.query(Tender).filter(Tender.created_at >= week_ago).count()
    
    # Unnotified tenders
    unnotified = db.query(Tender).filter(Tender.is_notified == False).count()
    
    return {
        "total_tenders": total_tenders,
        "passed_screening": passed_screening,
        "failed_screening": failed_screening,
        "recent_tenders_7_days": recent_tenders,
        "unnotified_tenders": unnotified,
        "last_updated": datetime.utcnow().isoformat()
    }
