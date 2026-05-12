"""
Pydantic schemas for authentication.
"""
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional


class LoginRequest(BaseModel):
    """POST /auth/login request body."""
    employee_code: str
    password: str

    @field_validator("employee_code")
    @classmethod
    def employee_code_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Employee code is required")
        return v.strip().upper()

    @field_validator("password")
    @classmethod
    def password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("Password is required")
        return v


class PasswordChangeRequest(BaseModel):
    """POST /auth/change-password request body."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class PasswordResetRequest(BaseModel):
    """POST /auth/reset-password (admin-only) request body."""
    employee_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    password_reset_required: bool = False
    user: "UserProfile"


class UserProfile(BaseModel):
    id: int
    employee_code: str
    email: str
    full_name: str
    role: str
    department: Optional[str] = None

    class Config:
        from_attributes = True


class TokenPayload(BaseModel):
    sub: str  # employee email
    employee_id: int
    role: str
    exp: int


# Rebuild model refs
TokenResponse.model_rebuild()
