"""
Authentication package: routes, JWT/password helpers, and FastAPI dependencies.

- ``router``: login and /me endpoints (mount under /api/v1/auth).
- ``admin_router``: super-admin user onboarding (mount under /api/v1/admin).
- ``get_current_user``: dependency for protecting other route modules.
"""
from app.auth.admin_router import router as admin_router
from app.auth.deps import get_current_user, require_super_admin
from app.auth.router import router

__all__ = ["router", "admin_router", "get_current_user", "require_super_admin"]
