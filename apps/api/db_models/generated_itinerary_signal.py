from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class GeneratedItinerarySignal(Base):
    """Implicit quality signals for one `generated_itineraries` Qdrant point
    (issue #34: the learning-flywheel quality_score background task).

    One row per `generation_id` (the same point id `ItineraryResponse.
    generation_id` hands back to the client — see
    services/generated_itineraries.py::compute_generation_id). Signals
    accumulate here as the frontend reports them (session duration,
    regenerated, shared, post-gen chat turns); the scheduler job in
    core/scheduler.py periodically reads rows whose session looks finished,
    runs them through `_compute_quality_score()`, writes the result onto the
    Qdrant point's payload, and stamps `scored_at` so it isn't rescored.

    `generation_id` is a `String`, not the Qdrant client's native int point
    id type, because it round-trips through this table, JSON API payloads,
    and frontend state as plain text — converted back to `int` only at the
    Qdrant call site, mirroring `store_generated_itinerary`'s own
    `point_id: str | None` parameter.
    """

    __tablename__ = "generated_itinerary_signals"

    generation_id: Mapped[str] = mapped_column(String(40), primary_key=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    regenerated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    session_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    post_gen_chat_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Bumped on every signal write — the scheduler's "session looks over"
    # fallback heuristic (no explicit session_duration report, e.g. the user
    # closed the tab without triggering `beforeunload`) uses this as a
    # quiet-period timeout rather than waiting forever.
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Null until the scheduler job has computed and written quality_score for
    # this generation — the job's "ready to score" query filter.
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
