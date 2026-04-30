"""
Tender API Routes
CRUD operations for tenders
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.tender import DetailedTender, Tender
from app.repositories.tender_repository import TenderRepository

router = APIRouter()


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _deadline_calendar_date(dt: Optional[datetime]) -> Optional[date]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).date()
    return dt.date()


def serialize_detailed_info(detailed: DetailedTender) -> Dict[str, Any]:
    """
    Shape detailed tender for API responses.
    Recomputes date_validation.deadline_status from stored deadline vs today's UTC date
    so UI 'expired' / 'active' views stay correct without re-running Agent 2.
    """
    dv_in = detailed.date_validation if isinstance(detailed.date_validation, dict) else {}
    dv: Dict[str, Any] = dict(dv_in)

    deadline_dt = detailed.deadline
    deadline_iso = deadline_dt.isoformat() if deadline_dt else None
    dline_date = _deadline_calendar_date(deadline_dt)

    if dline_date is not None:
        today = _utc_today()
        days_until = (dline_date - today).days
        dv["days_until_deadline"] = days_until
        if days_until < 0:
            dv["deadline_status"] = "expired"
            dv["urgency_level"] = "expired"
        elif days_until <= 7:
            dv["deadline_status"] = "urgent"
            dv.setdefault("urgency_level", "high")
        else:
            dv["deadline_status"] = "active"
            dv.setdefault("urgency_level", dv.get("urgency_level") or "low")

    result: Dict[str, Any] = {
        "detailed_title": detailed.detailed_title,
        "detailed_description": detailed.detailed_description,
        "requirements": detailed.requirements,
        "deadline": deadline_iso,
        "tender_value": detailed.tender_value,
        "duration": detailed.duration,
        "contact_info": detailed.contact_info,
        "additional_details": detailed.additional_details,
        "processing_status": detailed.processing_status,
        "processed_at": detailed.processed_at.isoformat() if detailed.processed_at else None,
    }
    if dv:
        result["date_validation"] = dv
    return result


def detailed_info_list_summary(detailed: DetailedTender) -> Dict[str, Any]:
    """Smaller payload for GET /tenders/ list (deadline + validation + title)."""
    full = serialize_detailed_info(detailed)
    out: Dict[str, Any] = {}
    if full.get("detailed_title"):
        out["detailed_title"] = full["detailed_title"]
    if full.get("deadline"):
        out["deadline"] = full["deadline"]
    if full.get("date_validation"):
        out["date_validation"] = full["date_validation"]
    return out


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
        tenders = (
            db.query(Tender)
            .options(joinedload(Tender.detailed_tender))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
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
    
    rows = []
    for tender in tenders:
        row = {
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
            "page_name": tender.page.name if tender.page else None,
        }
        if tender.detailed_tender:
            summary = detailed_info_list_summary(tender.detailed_tender)
            if summary:
                row["detailed_info"] = summary
        rows.append(row)
    return rows


@router.get("/stats/summary")
async def get_tender_stats(db: Session = Depends(get_db)):
    """Get tender statistics (static path must be registered before /{tender_id})."""
    total_tenders = db.query(Tender).count()
    passed_screening = db.query(Tender).filter(Tender.passes_screening == True).count()
    failed_screening = db.query(Tender).filter(Tender.passes_screening == False).count()

    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_tenders = db.query(Tender).filter(Tender.created_at >= week_ago).count()

    unnotified = db.query(Tender).filter(Tender.is_notified == False).count()

    return {
        "total_tenders": total_tenders,
        "passed_screening": passed_screening,
        "failed_screening": failed_screening,
        "recent_tenders_7_days": recent_tenders,
        "unnotified_tenders": unnotified,
        "last_updated": datetime.utcnow().isoformat(),
    }


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
        result["detailed_info"] = serialize_detailed_info(detailed_tender)

    return result
