"""
API Router Configuration
Main router that includes all API routes
"""
from fastapi import APIRouter

from app.api.routes import tenders, pages, keywords, system

api_router = APIRouter()

# Include all route modules
api_router.include_router(
    tenders.router,
    prefix="/tenders",
    tags=["tenders"]
)

api_router.include_router(
    pages.router,
    prefix="/pages",
    tags=["pages"]
)

api_router.include_router(
    keywords.router,
    prefix="/keywords",
    tags=["keywords"]
)

api_router.include_router(
    system.router,
    prefix="/system",
    tags=["system"]
)
