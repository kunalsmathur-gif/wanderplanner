from __future__ import annotations
from typing import Optional
from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class RefreshToken(Base):
    """Rotating refresh tokens for session persistence across visits.

    Only the SHA-256 hash of the token is stored — the raw token lives only in
    the httpOnly cookie on the client. Compromise of the DB alone cannot be
    used to mint sessions.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Best-effort device context for session management / abuse detection.
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # hashed, never raw IP

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
