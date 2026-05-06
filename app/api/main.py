"""
API Router Configuration
Main router that includes all API routes
"""
from fastapi import APIRouter, Depends

from app.auth import get_current_user, router as auth_router
from app.auth.admin_router import router as admin_router
from app.api.routes import tenders, pages, keywords, system, backup

api_router = APIRouter()

api_router.include_router(
    auth_router,
    prefix="/auth",
    tags=["auth"]
)

api_router.include_router(
    admin_router,
    prefix="/admin",
    tags=["admin"],
)

# Include all route modules
api_router.include_router(
    tenders.router,
    prefix="/tenders",
    tags=["tenders"],
    dependencies=[Depends(get_current_user)]
)

api_router.include_router(
    pages.router,
    prefix="/pages",
    tags=["pages"],
    dependencies=[Depends(get_current_user)]
)

api_router.include_router(
    keywords.router,
    prefix="/keywords",
    tags=["keywords"],
    dependencies=[Depends(get_current_user)]
)

api_router.include_router(
    system.router,
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(get_current_user)]
)

api_router.include_router(
    backup.router,
    prefix="/backup",
    tags=["backup"],
    dependencies=[Depends(get_current_user)],
)
