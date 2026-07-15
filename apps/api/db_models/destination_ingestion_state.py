from __future__ import annotations
from typing import Optional
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class DestinationIngestionState(Base):
    """Tracks demand-driven ingestion per destination (docs/scaling-tech-challenges.md §8).

    One row per destination that has ever been requested. Existence of a row
    (and how stale its `*_last_ingested_at` columns are) drives both the
    on-demand gatekeeper (services/destination_ingestion.py) and the
    scheduler's refresh loop (core/scheduler.py), replacing the fixed
    KNOWN_DESTINATIONS list with real usage.
    """

    __tablename__ = "destination_ingestion_state"

    destination: Mapped[str] = mapped_column(String(120), primary_key=True)
    osm_last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    wiki_last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
