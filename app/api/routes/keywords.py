"""
Keywords API Routes
CRUD operations for keywords
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.repositories.keyword_repository import KeywordRepository
from app.models.keyword import Keyword

router = APIRouter()

class KeywordCreate(BaseModel):
    keyword: str
    category: str  # e.g. sector, activity_fit, geography, source_tag
    description: Optional[str] = None
    case_sensitive: bool = False

class KeywordUpdate(BaseModel):
    keyword: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    case_sensitive: Optional[bool] = None
    is_active: Optional[bool] = None

@router.get("/", response_model=List[dict])
async def get_keywords(
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get keywords with optional filtering"""
    keyword_repo = KeywordRepository()
    
    if category:
        if active_only:
            keywords = db.query(Keyword).filter(
                Keyword.category == category,
                Keyword.is_active == True
            ).all()
        else:
            keywords = db.query(Keyword).filter(Keyword.category == category).all()
    else:
        if active_only:
            keywords = db.query(Keyword).filter(Keyword.is_active == True).all()
        else:
            keywords = keyword_repo.get_all_keywords(db)
    
    return [
        {
            "id": keyword.id,
            "keyword": keyword.keyword,
            "category": keyword.category,
            "description": keyword.description,
            "is_active": keyword.is_active,
            "case_sensitive": keyword.case_sensitive,
            "created_at": keyword.created_at.isoformat(),
            "updated_at": keyword.updated_at.isoformat()
        }
        for keyword in keywords
    ]

@router.get("/categories/stats")
async def get_keyword_stats(db: Session = Depends(get_db)):
    """Get keyword statistics by category (must be declared before /{keyword_id})."""
    total_count = db.query(Keyword).filter(Keyword.is_active == True).count()
    inactive_count = db.query(Keyword).filter(Keyword.is_active == False).count()
    categories = [
        row[0]
        for row in db.query(Keyword.category).distinct().all()
        if row[0] is not None
    ]
    
    return {
        "total_active": total_count,
        "total_inactive": inactive_count,
        "categories": categories,
    }

@router.get("/{keyword_id}")
async def get_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """Get a specific keyword"""
    keyword_repo = KeywordRepository()
    keyword = keyword_repo.get_keyword_by_id(db, keyword_id)
    
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    return {
        "id": keyword.id,
        "keyword": keyword.keyword,
        "category": keyword.category,
        "description": keyword.description,
        "is_active": keyword.is_active,
        "case_sensitive": keyword.case_sensitive,
        "created_at": keyword.created_at.isoformat(),
        "updated_at": keyword.updated_at.isoformat()
    }

@router.post("/", response_model=dict)
async def create_keyword(keyword_data: KeywordCreate, db: Session = Depends(get_db)):
    """Create a new keyword"""
    keyword_repo = KeywordRepository()
    
    # Check if keyword already exists in the same category
    existing = db.query(Keyword).filter(
        Keyword.keyword == keyword_data.keyword,
        Keyword.category == keyword_data.category
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Keyword already exists in this category")
    
    keyword = keyword_repo.create_keyword(
        db,
        keyword=keyword_data.keyword,
        category=keyword_data.category,
        description=keyword_data.description,
        case_sensitive=keyword_data.case_sensitive
    )
    
    return {
        "id": keyword.id,
        "keyword": keyword.keyword,
        "category": keyword.category,
        "message": "Keyword created successfully"
    }

@router.put("/{keyword_id}")
async def update_keyword(keyword_id: int, keyword_data: KeywordUpdate, db: Session = Depends(get_db)):
    """Update a keyword"""
    keyword_repo = KeywordRepository()
    
    update_data = keyword_data.dict(exclude_unset=True)
    
    keyword = keyword_repo.update_keyword(db, keyword_id, **update_data)
    
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    return {
        "id": keyword.id,
        "keyword": keyword.keyword,
        "category": keyword.category,
        "message": "Keyword updated successfully"
    }

@router.delete("/{keyword_id}")
async def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    """Delete a keyword"""
    keyword_repo = KeywordRepository()
    
    success = keyword_repo.delete_keyword(db, keyword_id)
    if not success:
        raise HTTPException(status_code=404, detail="Keyword not found")
    
    return {"message": "Keyword deleted successfully"}
