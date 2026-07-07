from __future__ import annotations
from typing import Optional
from datetime import datetime
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class Event(Base):
    """Append-only analytics event log powering the admin dashboard.

    Kept intentionally generic (event_type + jsonb metadata) so new event
    kinds don't require schema migrations. `user_id` is nullable to allow
    pre-login/anonymous session_start events.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # e.g. "session_start", "signup", "login_success", "login_failed",
    # "itinerary_generated", "itinerary_failed"
    event_type: Mapped[str] = mapped_column(String(64), index=True)

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_metadata: Mapped[Optional[dict]] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
