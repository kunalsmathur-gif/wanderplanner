from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class PoiProviderUsage(Base):
    """One row per per-destination POI ingestion attempt during the Google
    Places vs OSM trial (2026-08-26 -> `settings.google_places_trial_end_date`).

    Backs `scripts/poi_provider_eval_report.py` — the trial's whole point is
    to make the "keep paying for Google Places after October or drop back to
    OSM-only" call from real data (call volume, estimated $ spent, and
    fallback frequency) rather than a subjective read of a handful of
    destinations. Every row is written by `scrapers/poi_provider.py`
    regardless of which provider ultimately served the POIs, so the report can
    compute both sides' effective hit rate.
    """

    __tablename__ = "poi_provider_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    destination: Mapped[str] = mapped_column(String(200), index=True)
    # "google_places" | "osm" — whichever source's POIs were actually written
    # this run (Google Places may have been *attempted* but failed, in which
    # case this is "osm" and `google_places_attempted`/`google_places_error`
    # record what happened).
    provider_used: Mapped[str] = mapped_column(String(20))
    google_places_attempted: Mapped[bool] = mapped_column(Boolean, default=False)
    google_places_call_count: Mapped[int] = mapped_column(Integer, default=0)
    google_places_poi_count: Mapped[int] = mapped_column(Integer, default=0)
    google_places_estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    google_places_error: Mapped[str] = mapped_column(String(500), default="")
    osm_poi_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
