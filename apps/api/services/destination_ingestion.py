"""Demand-driven destination ingestion gatekeeper (docs/scaling-tech-challenges.md §8).

Eagerly pre-ingesting every populated place on Earth doesn't scale (see §8
for the math) — the corpus should grow with actual user demand instead.
`ensure_destination_ingested()` is the single entry point: on a destination's
first-ever request it geocode-validates (rejecting junk input before
spending Overpass/embedding budget), ingests OSM POIs + Wikivoyage inline,
and records the timestamp row. Subsequent requests just bump the demand
counters — no ingestion, no first-request latency penalty.

Best-effort by design: any failure here must never block itinerary
generation, which already has its own knowledge to fall back on.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from db import AsyncSessionLocal
from db_models import DestinationIngestionState
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

# Stampede guard: N concurrent first requests for the same new destination
# ingest once, not N times — same pattern as services/gems.py.
_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


async def ensure_destination_ingested(destination: str) -> None:
    if not destination or not destination.strip():
        return
    destination = destination.strip()

    async with _locks_guard:
        lock = _locks.setdefault(destination, asyncio.Lock())

    async with lock:
        async with AsyncSessionLocal() as db:
            row = await db.get(DestinationIngestionState, destination)
            now = datetime.now(timezone.utc)

            if row is not None:
                row.request_count += 1
                row.last_requested_at = now
                await db.commit()
                return

            # First-ever request for this destination. Geocode-validate first
            # so a misspelled/junk destination never reaches Overpass/embedding.
            try:
                await geocode_city(destination)
            except Exception:
                logger.info("Skipping ingestion for ungeocodable destination %r", destination)
                return

            osm_count = 0
            try:
                from scrapers.osm import ingest_osm_pois
                from scrapers.wikivoyage import ingest_wikivoyage
                osm_count, _ = await asyncio.gather(
                    ingest_osm_pois(destination),
                    ingest_wikivoyage(destination),
                )
            except Exception:
                logger.warning("Ingestion failed for new destination %r", destination, exc_info=True)

            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=now,
                wiki_last_ingested_at=now,
                request_count=1,
                last_requested_at=now,
            ))
            await db.commit()
            logger.info("First-request ingestion complete for %r (%d OSM POIs)", destination, osm_count or 0)
