"""
JWT token utilities, current-user dependency, role-based access control,
and password hashing (bcrypt via passlib).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.employee import Employee

logger = logging.getLogger(__name__)
settings = get_settings()
security_scheme = HTTPBearer()

# ── Password hashing (bcrypt) ──────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# ── Token creation ──────────────────────────────────────
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# ── Token verification ─────────────────────────────────
def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Current user dependency ────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    """FastAPI dependency — extracts and validates the current user from JWT."""
    payload = decode_token(credentials.credentials)
    email: str = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    # Normalize email for robust matching
    email = email.strip().lower()

    result = await db.execute(
        select(Employee).where(
            func.lower(Employee.email) == email,
            Employee.is_active == True,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("Auth failed: no active employee for email '%s'", email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active employee account found. Contact your administrator.",
        )

    logger.info("User authenticated: %s (id=%d, role=%s)", email, user.id, user.role)
    return user


# ── Role-based access control ──────────────────────────
def require_role(*allowed_roles: str):
    """
    Dependency factory that restricts access to specific roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("ADMIN"))])
    """
    async def role_checker(
        current_user: Employee = Depends(get_current_user),
    ) -> Employee:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to roles: {', '.join(allowed_roles)}",
            )
        return current_user

    return role_checker
