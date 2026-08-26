"""POI provider orchestrator — decides Google Places vs OSM per ingestion
run during the trial window (core/config.py's "Google Places POI trial"
block) and records which provider actually served the data.

Policy (2026-08-26 -> `settings.google_places_trial_end_date`):
  1. Before the trial end date: try Google Places first (richer India
     coverage/ratings/freshness). On ANY failure (`GooglePlacesQuotaError`,
     network error, empty result), fall back to the existing free OSM/
     Overpass pipeline so POI ingestion never goes to zero.
  2. On/after the trial end date: skip Google Places entirely and go
     straight to OSM — regardless of whether credits are technically still
     available, per the user's "fallback to OSM once the period is over"
     instruction. This is a hard date check, not a credits-remaining check,
     because credit *balance* isn't observable from this API — only Google's
     billing console shows that, and the trial's whole point is to make the
     keep/drop call before hitting an unexpected bill.
  3. Every attempt (successful or not) writes one `PoiProviderUsage` row so
     `scripts/poi_provider_eval_report.py` can compare the two providers on
     real production data before the trial ends.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from core.config import settings
from db import AsyncSessionLocal
from db_models import PoiProviderUsage
from scrapers.google_places import (
    GooglePlacesQuotaError,
    estimate_cost_usd,
    fetch_google_places_pois,
)

logger = logging.getLogger(__name__)

PROVIDER_GOOGLE_PLACES = "google_places"
PROVIDER_OSM = "osm"


def trial_active(today: date | None = None) -> bool:
    """True if Google Places should even be attempted today. A malformed
    `google_places_trial_end_date` fails safe to "trial over" (OSM-only)
    rather than risking an indefinite paid trial from a typo'd date."""
    today = today or datetime.now(UTC).date()
    try:
        end_date = date.fromisoformat(settings.google_places_trial_end_date)
    except ValueError:
        logger.error(
            "Invalid google_places_trial_end_date=%r — treating the Google Places trial as OVER "
            "(falling back to OSM-only) rather than risk it running indefinitely.",
            settings.google_places_trial_end_date,
        )
        return False
    return today <= end_date


async def _record_usage(
    destination: str,
    *,
    provider_used: str,
    google_places_attempted: bool,
    google_places_call_count: int = 0,
    google_places_poi_count: int = 0,
    google_places_error: str = "",
    osm_poi_count: int = 0,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(PoiProviderUsage(
                destination=destination,
                provider_used=provider_used,
                google_places_attempted=google_places_attempted,
                google_places_call_count=google_places_call_count,
                google_places_poi_count=google_places_poi_count,
                google_places_estimated_cost_usd=estimate_cost_usd(google_places_call_count),
                google_places_error=google_places_error[:500],
                osm_poi_count=osm_poi_count,
                created_at=datetime.now(UTC),
            ))
            await db.commit()
    except Exception:
        # Eval bookkeeping must never break the actual ingestion it's
        # measuring — same fire-and-forget contract as core/analytics.py.
        logger.exception("Failed to record POI provider usage for %r", destination)


async def _fallback_to_osm_ingest(
    destination: str, *, google_places_attempted: bool, google_places_call_count: int = 0,
    google_places_error: str = "",
) -> tuple[int, str]:
    """Delegate the actual OSM write to `scrapers.osm.ingest_osm_pois_with_
    outcome` — NOT a reimplemented embed+upsert — so the fallback path keeps
    OSM's own battle-tested guards (thin/single-category-dominated retry,
    degraded-geocode "keep existing data" protection, prominence-fetch
    checks). A generic re-upsert here would silently bypass all of that."""
    from scrapers.osm import ingest_osm_pois_with_outcome

    osm_count, _outcome = await ingest_osm_pois_with_outcome(destination)
    await _record_usage(
        destination, provider_used=PROVIDER_OSM, google_places_attempted=google_places_attempted,
        google_places_call_count=google_places_call_count, google_places_error=google_places_error,
        osm_poi_count=osm_count,
    )
    return osm_count, PROVIDER_OSM


async def fetch_pois_for_destination(destination: str) -> tuple[list[dict], str]:
    """Fetch POIs for `destination` via whichever provider the trial policy
    selects, returning `(pois, provider_used)` in `scrapers/osm.py`'s payload
    shape either way.

    NOTE: this is for callers that need the raw POI list (e.g. the eval
    report, or a caller doing its own write). It does NOT go through OSM's
    `ingest_osm_pois_with_outcome` guards — for the actual ingestion/write
    path use `ingest_pois()` below, which does.

    Does not raise on Google Places failure — that's exactly the case this
    function exists to absorb. Only OSM failures propagate, matching
    `fetch_osm_pois`'s existing contract (callers already handle that).
    """
    if not trial_active():
        from scrapers.osm import fetch_osm_pois
        osm_pois = await fetch_osm_pois(destination)
        await _record_usage(
            destination, provider_used=PROVIDER_OSM, google_places_attempted=False,
            osm_poi_count=len(osm_pois),
        )
        return osm_pois, PROVIDER_OSM

    try:
        gp_pois, call_count = await fetch_google_places_pois(destination)
    except Exception as e:
        logger.warning(
            "Google Places failed for %r (%s) — falling back to OSM for this run", destination, e,
        )
        from scrapers.osm import fetch_osm_pois
        osm_pois = await fetch_osm_pois(destination)
        await _record_usage(
            destination, provider_used=PROVIDER_OSM, google_places_attempted=True,
            google_places_error=str(e), osm_poi_count=len(osm_pois),
        )
        return osm_pois, PROVIDER_OSM

    if not gp_pois:
        # Empty is treated the same as a failure — a destination Google
        # Places genuinely has zero POIs for is vanishingly unlikely (it's
        # denser than OSM, not sparser), so an empty result is far more
        # likely a bad radius/geocode than real ground truth. OSM having
        # something for the same destination is strictly better than
        # reporting zero POIs.
        logger.info("Google Places returned 0 POIs for %r — falling back to OSM for this run", destination)
        from scrapers.osm import fetch_osm_pois
        osm_pois = await fetch_osm_pois(destination)
        await _record_usage(
            destination, provider_used=PROVIDER_OSM, google_places_attempted=True,
            google_places_call_count=call_count, osm_poi_count=len(osm_pois),
        )
        return osm_pois, PROVIDER_OSM

    await _record_usage(
        destination, provider_used=PROVIDER_GOOGLE_PLACES, google_places_attempted=True,
        google_places_call_count=call_count, google_places_poi_count=len(gp_pois),
    )
    return gp_pois, PROVIDER_GOOGLE_PLACES


async def ingest_pois(destination: str) -> tuple[int, str]:
    """Ingest POIs for `destination` (Google Places, falling back to OSM per
    trial policy) into the same `osm_pois` Qdrant collection OSM already
    writes to — this trial is a drop-in provider swap, not a new collection,
    so no downstream reader changes are needed.

    Returns `(poi_count, provider_used)`.

    Unlike `fetch_pois_for_destination`, this is the actual write path used
    by `core/scheduler.py`, so the OSM fallback branch delegates to
    `scrapers.osm.ingest_osm_pois_with_outcome` (see `_fallback_to_osm_
    ingest`) rather than reimplementing embed+upsert here — that keeps OSM's
    thin/degraded-geocode guards intact for the fallback case. Only the
    Google Places SUCCESS path does its own embed+upsert (there is no
    equivalent "guard" logic to preserve there — this trial only borrows
    OSM's write pipeline for OSM's own data).
    """
    if not trial_active():
        return await _fallback_to_osm_ingest(destination, google_places_attempted=False)

    try:
        gp_pois, call_count = await fetch_google_places_pois(destination)
    except Exception as e:
        logger.warning(
            "Google Places failed for %r (%s) — falling back to OSM for this run", destination, e,
        )
        return await _fallback_to_osm_ingest(
            destination, google_places_attempted=True, google_places_error=str(e),
        )

    if not gp_pois:
        logger.info("Google Places returned 0 POIs for %r — falling back to OSM for this run", destination)
        return await _fallback_to_osm_ingest(
            destination, google_places_attempted=True, google_places_call_count=call_count,
        )

    import asyncio

    from qdrant_client.models import PointStruct

    from core.embeddings import embed
    from core.qdrant import delete_stale_destination_points, get_qdrant
    from scrapers.google_places import poi_point_id

    texts = [p["text"] for p in gp_pois]
    vectors = await asyncio.to_thread(embed, texts)

    points = []
    new_ids: set[int] = set()
    for poi, vec in zip(gp_pois, vectors):
        point_id = poi_point_id(poi["destination"], poi["name"])
        new_ids.add(point_id)
        points.append(PointStruct(id=point_id, vector=vec, payload=poi))

    client = get_qdrant()
    stale_count = delete_stale_destination_points(client, settings.qdrant_collection_osm, destination, new_ids)
    if stale_count:
        logger.info(
            "Deleted %d stale POI points for %r before re-ingestion (provider=%s)",
            stale_count, destination, PROVIDER_GOOGLE_PLACES,
        )
    client.upsert(collection_name=settings.qdrant_collection_osm, points=points)

    await _record_usage(
        destination, provider_used=PROVIDER_GOOGLE_PLACES, google_places_attempted=True,
        google_places_call_count=call_count, google_places_poi_count=len(points),
    )
    return len(points), PROVIDER_GOOGLE_PLACES
