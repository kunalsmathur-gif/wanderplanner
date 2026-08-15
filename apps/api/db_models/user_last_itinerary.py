from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class UserLastItinerary(Base):
    """A logged-in user's single most-recently-generated itinerary (issue
    #65) — an upsert-only row, not a history table. `user_id` is both the
    primary key and the unique FK, which is what makes "one row per user"
    structural rather than an application-level invariant a second writer
    could violate.

    Written best-effort/non-blocking after a successful live generation (see
    services/user_last_itinerary.py — same `try/except: pass` +
    fire-and-forget discipline as `services/itinerary_cache.py`/
    `services/generated_itineraries.py`), so a write failure here can never
    affect the itinerary already streamed to the client.
    """

    __tablename__ = "user_last_itinerary"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    trip_config_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    itinerary_json: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
