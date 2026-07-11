"""FastAPI dependency for resolving the current authenticated user from the
access-token cookie. Used to gate itinerary generation and admin endpoints —
this is the server-side enforcement point; the frontend redirect is UX only
and must never be relied on alone.
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import decode_access_token
from db import get_db
from db_models import User

ACCESS_TOKEN_COOKIE = "wp_access_token"
REFRESH_TOKEN_COOKIE = "wp_refresh_token"


async def get_current_user(
    wp_access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not wp_access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = decode_access_token(wp_access_token)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or disabled")

    return user


async def get_current_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_optional_user(
    wp_access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Non-raising variant — used for endpoints that log analytics for both
    anonymous and authenticated requests."""
    if not wp_access_token:
        return None
    user_id = decode_access_token(wp_access_token)
    if user_id is None:
        return None
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    return result.scalar_one_or_none()
