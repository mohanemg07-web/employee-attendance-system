"""
Authentication router — Enterprise employee_code + password login.

Provides:
- /auth/login            → Authenticate with employee_code + password, issue JWT
- /auth/me               → Return current user profile
- /auth/change-password  → Change own password (required on first login)
- /auth/reset-password   → Admin-only: reset another user's password
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.employee import Employee
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    TokenResponse,
    UserProfile,
)
from app.utils.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)

logger = logging.getLogger(__name__)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Login ───────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate an employee with employee_code + password.
    Returns a JWT access token and user profile.
    """
    # Normalize employee code
    code = body.employee_code.strip().upper()

    # ── Lookup employee by code ──────────────────────────
    result = await db.execute(
        select(Employee).where(
            sa_func.upper(Employee.employee_code) == code,
            Employee.is_active == True,
        )
    )
    employee = result.scalar_one_or_none()

    if not employee:
        logger.warning("Login attempt: no active employee for code '%s'", code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee code or password.",
        )

    # ── Account lockout check ────────────────────────────
    if employee.account_locked_until and employee.account_locked_until > datetime.now(timezone.utc):
        remaining = (employee.account_locked_until - datetime.now(timezone.utc)).seconds // 60
        logger.warning("Login blocked: account '%s' is locked for %d more minutes", code, remaining)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account is locked due to too many failed attempts. Try again in {remaining + 1} minute(s).",
        )

    # ── Password verification ────────────────────────────
    if not employee.password_hash:
        # Account has no password set yet — reject login
        logger.warning("Login attempt: employee '%s' has no password set", code)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not activated. Contact your administrator.",
        )

    if not verify_password(body.password, employee.password_hash):
        # ── Increment failure count ──────────────────────
        employee.failed_login_attempts = (employee.failed_login_attempts or 0) + 1

        if employee.failed_login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
            employee.account_locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCOUNT_LOCKOUT_MINUTES
            )
            logger.warning(
                "Account '%s' locked after %d failed attempts",
                code,
                employee.failed_login_attempts,
            )

        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid employee code or password.",
        )

    # ── Success — reset failures, update last_login ──────
    employee.failed_login_attempts = 0
    employee.account_locked_until = None
    employee.last_login = datetime.now(timezone.utc)
    await db.flush()

    # ── Issue JWT ────────────────────────────────────────
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    app_token = create_access_token(
        data={
            "sub": employee.email,
            "employee_id": employee.id,
            "role": employee.role,
        },
        expires_delta=expires,
    )

    logger.info("Login success: %s (id=%d, role=%s)", code, employee.id, employee.role)

    return TokenResponse(
        access_token=app_token,
        token_type="bearer",
        expires_in=int(expires.total_seconds()),
        password_reset_required=bool(employee.password_reset_required),
        user=UserProfile(
            id=employee.id,
            employee_code=employee.employee_code,
            email=employee.email,
            full_name=employee.full_name,
            role=employee.role,
            department=employee.department,
        ),
    )


# ── Current user profile ───────────────────────────────
@router.get("/me", response_model=UserProfile)
async def get_me(
    current_user: Employee = Depends(get_current_user),
):
    """Return the authenticated user's profile."""
    return UserProfile(
        id=current_user.id,
        employee_code=current_user.employee_code,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        department=current_user.department,
    )


# ── Change password ────────────────────────────────────
@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the authenticated user's password.
    Required on first login when password_reset_required is true.
    """
    # Verify current password
    if not current_user.password_hash or not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    # Prevent reusing the same password
    if verify_password(body.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password cannot be the same as the current password.",
        )

    current_user.password_hash = hash_password(body.new_password)
    current_user.password_reset_required = False
    await db.flush()

    logger.info("Password changed for employee %s (id=%d)", current_user.employee_code, current_user.id)
    return {"message": "Password changed successfully."}


# ── Admin: reset another user's password ───────────────
@router.post("/reset-password")
async def reset_password(
    body: PasswordResetRequest,
    admin_user: Employee = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin-only: Reset an employee's password to the system default
    and flag their account for mandatory password change on next login.
    """
    code = body.employee_code.strip().upper()
    result = await db.execute(
        select(Employee).where(
            sa_func.upper(Employee.employee_code) == code,
        )
    )
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{code}' not found.",
        )

    target.password_hash = hash_password(settings.DEFAULT_ADMIN_PASSWORD)
    target.password_reset_required = True
    target.failed_login_attempts = 0
    target.account_locked_until = None
    await db.flush()

    logger.info(
        "Password reset by admin %s for employee %s",
        admin_user.employee_code,
        code,
    )
    return {"message": f"Password for {code} has been reset. They must change it on next login."}
