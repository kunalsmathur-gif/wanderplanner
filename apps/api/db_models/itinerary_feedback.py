from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ItineraryFeedback(Base):
    """A consumer-side feedback signal on a generated itinerary.

    Captures both a whole-itinerary "missed the mark" flag and a per-day/place
    thumbs-up/down reaction, always tied to a snapshot of the TripConfig that
    produced the itinerary (not a bare itinerary ID, since one isn't persisted
    today) so the request context survives even if the live trip config is
    later edited or regenerated.
    """

    __tablename__ = "itinerary_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trip_config_snapshot: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    day_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    place_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sentiment: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
