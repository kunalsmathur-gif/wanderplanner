from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)
    consent_accepted: bool = Field(
        description="Must be true — user accepted the Terms of Service / Privacy Policy at signup."
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    is_admin: bool
    auth_provider: str  # "password" | "google"


class GoogleCallbackError(BaseModel):
    detail: str


class AdminAccessRequestCreate(BaseModel):
    message: str | None = Field(default=None, max_length=500)


class AdminRequestResponse(BaseModel):
    id: str
    user_id: str
    user_email: str | None
    user_display_name: str | None
    status: str  # "pending" | "approved" | "rejected"
    message: str | None
    created_at: str
    reviewed_at: str | None
