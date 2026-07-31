from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class AgentLead(Base):
    """A human-handoff lead created from an itinerary CTA.

    Stores the minimum trip/contact context needed to follow up personally,
    measure response-SLA adherence, and manually mark downstream conversion
    until a fuller booking stack exists.
    """

    __tablename__ = "agent_leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    destination: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    trip_config_summary: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    # Optional free-text ask from the traveler (max 100 words, enforced in
    # models/agent_leads.py). Not the itinerary/PDF itself — those are only
    # emailed to the agent, not persisted, to avoid duplicating the
    # itinerary store and bloating this table.
    custom_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reassurance_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marked_booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
