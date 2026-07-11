from __future__ import annotations
from typing import Optional
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class User(Base):
    """A registered account. Password auth and Google SSO both populate this table;
    OTP/mobile auth is reserved (phone/otp columns) for a future iteration.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Contact identifiers — at least one of email/google_sub must be set.
    # Stored as-is at the DB layer; TLS in transit + disk-level encryption
    # (managed Postgres provider, e.g. RDS/Cloud SQL encryption-at-rest) covers
    # PII at rest. Never log these fields (see core/logging_config.py filters).
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, index=True, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True, nullable=True)

    # Argon2id hash — never store/compare plaintext passwords.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Google "sub" claim — stable unique identifier for SSO-linked accounts.
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)

    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Consent timestamp for signup ToS/privacy policy acceptance — required
    # for DPDP/GDPR-style consent recordkeeping.
    consent_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
