"""
First-run / default admin creation and company-email rules.
"""
from typing import List

from sqlalchemy.orm import Session

from app.auth.security import get_password_hash
from app.core.config import settings
from app.models.user import User


def allowed_domains() -> List[str]:
    return [d.strip().lower() for d in settings.ALLOWED_COMPANY_EMAIL_DOMAINS.split(",") if d.strip()]


def is_company_email(email: str) -> bool:
    email_domain = email.split("@")[-1].lower()
    return email_domain in allowed_domains()


def ensure_default_admin(db: Session) -> None:
    """Create bootstrap admin if missing (must match configured domain rules)."""
    existing = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL.lower()).first()
    if existing:
        return

    if not is_company_email(settings.DEFAULT_ADMIN_EMAIL):
        return

    admin_user = User(
        email=settings.DEFAULT_ADMIN_EMAIL.lower(),
        full_name="Default Admin",
        hashed_password=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
        role="super_admin",
        is_active=True,
        is_superuser=True,
    )
    db.add(admin_user)
    db.commit()
