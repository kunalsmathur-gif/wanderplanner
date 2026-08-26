from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class JobRunState(Base):
    """Persists the last successful completion time of scheduler jobs whose
    cadence is NOT already gated by their own domain state (contrast with
    `DestinationIngestionState`, which already self-gates `_refresh_osm_pois`/
    `_refresh_youtube_comments` per-destination via DB timestamps).

    Root cause this fixes: `AsyncIOScheduler`'s default in-memory job store
    means every `IntervalTrigger` recomputes its next-fire time from *process
    start*, not from when the job last actually completed. A job with no
    persisted state of its own (`_refresh_reddit`, `_refresh_itinerary_corpus`,
    `_refresh_visa_info`) would silently reset its cadence clock on every
    deploy/restart — in the worst case (restarts more frequent than the
    configured interval) never firing at all. Storing `last_run_at` here
    lets a job's *outer* trigger run on a short, cheap "check" cadence while
    the job itself only does real work once truly due, independent of how
    often the process restarts.
    """

    __tablename__ = "job_run_state"

    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
