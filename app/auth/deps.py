"""
FastAPI dependencies: Bearer JWT + current user resolution.
Uses HTTPBearer (not OAuth2PasswordBearer) so browser/clients send a plain
``Authorization: Bearer <token>`` header consistently with axios/fetch.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth.security import ALGORITHM
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

security_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise credentials_exception
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Only bootstrap super admins (`super_admin` role or `is_superuser`)."""
    if current_user.role != "super_admin" and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


_ANALYST_OR_ABOVE = {"analyst", "admin", "super_admin"}
_ADMIN_OR_ABOVE = {"admin", "super_admin"}


def require_analyst_or_above(current_user: User = Depends(get_current_user)) -> User:
    """Allow analyst, admin, and super_admin. Block viewer."""
    if current_user.role not in _ANALYST_OR_ABOVE and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analyst access or higher is required to perform this action",
        )
    return current_user


def require_admin_or_above(current_user: User = Depends(get_current_user)) -> User:
    """Allow admin and super_admin. Block viewer/analyst."""
    if current_user.role not in _ADMIN_OR_ABOVE and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access or higher is required for this action",
        )
    return current_user


# ekKsh5@V.G@4jJN