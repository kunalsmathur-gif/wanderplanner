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
from collections import deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.config import settings
from db import AsyncSessionLocal
from db_models import DestinationIngestionState
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

# Stampede guard: N concurrent first requests for the same new destination
# ingest once, not N times — same pattern as services/gems.py.
_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()

# Cold-start rate limit (docs/scaling-tech-challenges.md §8 item 5): first-ever
# requests for a destination are the expensive path (Overpass + Wikivoyage +
# embeddings), unlike the cheap counter-bump for already-ingested ones. With no
# cap, garbage/spam input naming many distinct fake destinations could run up
# Overpass/Gemini spend unbounded. This is a process-global sliding-window cap
# (not per-IP/session — no caller identity reaches this function today; adding
# that would need request-context plumbing through chains/itinerary_chain.py,
# a bigger change than this guard rail) — cheap first line of defense.
_MAX_COLD_STARTS_PER_HOUR = 5
_cold_start_window = timedelta(hours=1)
_cold_start_times: deque[datetime] = deque()
_cold_start_guard = asyncio.Lock()


async def _cold_start_budget_available() -> bool:
    """Reserve one of the hour's cold-start slots, or return False if exhausted."""
    async with _cold_start_guard:
        now = datetime.now(timezone.utc)
        cutoff = now - _cold_start_window
        while _cold_start_times and _cold_start_times[0] < cutoff:
            _cold_start_times.popleft()
        if len(_cold_start_times) >= _MAX_COLD_STARTS_PER_HOUR:
            return False
        _cold_start_times.append(now)
        return True


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

            if not await _cold_start_budget_available():
                logger.warning(
                    "Cold-start ingestion budget exhausted (%d/hour) — skipping first-request "
                    "ingestion for %r this cycle",
                    _MAX_COLD_STARTS_PER_HOUR,
                    destination,
                )
                return

            # First-ever request for this destination. Geocode-validate first
            # so a misspelled/junk destination never reaches Overpass/embedding.
            try:
                await geocode_city(destination)
            except Exception:
                logger.info("Skipping ingestion for ungeocodable destination %r", destination)
                return

            osm_count = 0
            wiki_count = 0
            youtube_count = 0
            youtube_attempted = False
            try:
                from scrapers.osm import ingest_osm_pois
                from scrapers.wikivoyage import ingest_wikivoyage

                tasks = [ingest_osm_pois(destination), ingest_wikivoyage(destination)]

                # YouTube comments are the hidden-gems sentiment source
                # (services/gems.py). Unlike OSM/Wikivoyage — free, unmetered
                # public APIs — this spends a real metered quota, which is why
                # it stayed manual-only until now. It's safe to run
                # automatically because scrapers/youtube_comments.py enforces
                # its own rolling-24h search budget: over budget, it returns 0
                # rather than overspending, and the NULL youtube_last_ingested_at
                # left behind makes the scheduler pick the destination up later.
                youtube_attempted = bool(
                    settings.youtube_ingest_on_cold_start and settings.youtube_api_key
                )
                if youtube_attempted:
                    from scrapers.youtube_comments import ingest_youtube_comments
                    tasks.append(ingest_youtube_comments(destination))

                # return_exceptions: one source failing must not discard the
                # others' already-completed work (before YouTube was added a
                # raising OSM fetch also threw away a successful wiki scrape).
                results = await asyncio.gather(*tasks, return_exceptions=True)
                counts: list[int] = []
                for source_name, result in zip(("OSM", "Wikivoyage", "YouTube"), results):
                    if isinstance(result, Exception):
                        logger.warning(
                            "%s ingestion failed for new destination %r: %s",
                            source_name, destination, result, exc_info=result,
                        )
                        counts.append(0)
                    else:
                        counts.append(result or 0)
                osm_count, wiki_count = counts[0], counts[1]
                youtube_count = counts[2] if len(counts) > 2 else 0
            except Exception:
                logger.warning("Ingestion failed for new destination %r", destination, exc_info=True)

            if not osm_count and not wiki_count:
                # Both sources came back empty — Overpass/Wikivoyage may
                # both be transiently down, or the destination name may not
                # match either source's naming (found 2026-07-20: this
                # exact failure mode silently produced destinations with no
                # grounding data at all, with nothing surfacing it as an
                # error). Surface it loudly so it doesn't go unnoticed.
                logger.warning(
                    "First-request ingestion for %r returned zero OSM POIs and zero wiki chunks", destination
                )

            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=now,
                wiki_last_ingested_at=now,
                # Left NULL when YouTube wasn't attempted (no key / disabled)
                # or produced nothing (over budget, no videos, comments off) —
                # the scheduler's refresh loop treats NULL as "never ingested"
                # and retries it, so a quota-exhausted cold start self-heals.
                youtube_last_ingested_at=now if youtube_count else None,
                request_count=1,
                last_requested_at=now,
            ))
            await db.commit()
            logger.info(
                "First-request ingestion complete for %r (%d OSM POIs, %d wiki chunks, %d YouTube comments%s)",
                destination,
                osm_count or 0,
                wiki_count or 0,
                youtube_count or 0,
                "" if youtube_attempted else "; YouTube skipped",
            )
