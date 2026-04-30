"""Super-admin routes: onboard company users (no email invite yet — temporary password)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.bootstrap import allowed_domains, is_company_email
from app.auth.deps import require_super_admin
from app.auth.security import get_password_hash
from app.core.database import get_db
from app.models.user import User

router = APIRouter()

_ROLE_CREATE = Literal["viewer", "analyst", "admin"]


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = None
    role: _ROLE_CREATE = "viewer"


class CreatedUserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    role: str
    is_active: bool


@router.post("/users", response_model=CreatedUserResponse)
async def create_company_user(
    payload: CreateUserRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """
    Create a user account with a temporary password.
    Email must match configured company domains (same rule as login).
    Does not send email — share credentials securely outside the app for now.
    """
    email = payload.email.lower().strip()
    if not is_company_email(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only company emails are allowed. Allowed domains: {', '.join(allowed_domains())}",
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return CreatedUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
    )


class SetUserPasswordRequest(BaseModel):
    """Super-admin sets a new password for another company user (forgot-password support)."""

    email: EmailStr
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/users/set-password")
async def set_user_password(
    payload: SetUserPasswordRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """
    Set password for an existing user by email.
    Cannot be used on your own account — use Change password instead.
    Target must be a company-domain user that already exists.
    """
    email = payload.email.lower().strip()
    if email == admin.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use your account's Change password section to update your own password.",
        )

    if not is_company_email(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only company emails are allowed. Allowed domains: {', '.join(allowed_domains())}",
        )

    target = db.query(User).filter(User.email == email).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No user with this email.")

    target.hashed_password = get_password_hash(payload.new_password)
    db.add(target)
    db.commit()

    return {"success": True, "message": "Password updated. Ask the user to sign in with the new password."}
