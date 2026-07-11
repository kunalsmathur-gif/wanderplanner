"""Password hashing and JWT access/refresh token helpers.

Passwords: Argon2id via `argon2-cffi` (OWASP-recommended default parameters).
Tokens: short-lived JWT access tokens signed with HS256, plus opaque
refresh tokens whose SHA-256 hash (never the raw value) is persisted in
`refresh_tokens` so a DB leak alone can't be used to mint sessions.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.config import settings

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed/legacy hash, etc. — never raise on login, just reject.
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Return (raw_token, sha256_hash, expires_at). Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    return raw, token_hash, expires_at


def generate_password_reset_token() -> tuple[str, str, datetime]:
    """Return (raw_token, sha256_hash, expires_at) for the forgot-password flow."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.password_reset_token_ttl_minutes)
    return raw, token_hash, expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()
