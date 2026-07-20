"""Pilot re-ingestion batch (2026-07-20 session, NEXT_SESSION_TODO.md item 2).

Targets 8 priority destinations before a wider batch: the 6 India-domestic
metros (statistically likely POC-tester destinations, currently either
zero-data or food/drink-skewed from the pre-round-robin-fix OSM logic) plus
two major zero-data international cities (Paris, New York).

Re-ingests both OSM POIs and Wikivoyage text via the existing
ingest_osm_pois()/ingest_wikivoyage() (retry/backoff + stale-point cleanup
already built in — see scrapers/osm.py and scrapers/wikivoyage.py), then
upserts a destination_ingestion_state row so the scheduler picks these up
for future automatic refreshes.

Real writes against the production Qdrant Cloud cluster — this is a pilot
subset, not the full 136-destination backlog, by explicit user direction.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from collections import Counter

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reingest_pilot_batch")

# Delay between destinations (not between retry attempts within one fetch —
# that's handled separately inside fetch_osm_pois). Previous sessions hit
# Overpass rate limits at 12s; going longer here since this batch also
# includes internationally popular Paris/New York which see heavier organic
# Overpass traffic than most destinations.
DELAY_SECONDS = 15.0

DESTINATIONS = [
    "Mumbai", "Delhi", "Bengaluru", "Kochi", "Varanasi", "Agra",
    "Paris", "New York",
]


async def _reingest_one(destination: str) -> dict:
    from scrapers.osm import ingest_osm_pois
    from scrapers.wikivoyage import ingest_wikivoyage

    osm_count, wiki_count = await asyncio.gather(
        ingest_osm_pois(destination),
        ingest_wikivoyage(destination),
        return_exceptions=True,
    )
    result = {
        "destination": destination,
        "osm_count": osm_count if isinstance(osm_count, int) else 0,
        "wiki_count": wiki_count if isinstance(wiki_count, int) else 0,
        "osm_error": str(osm_count) if isinstance(osm_count, Exception) else None,
        "wiki_error": str(wiki_count) if isinstance(wiki_count, Exception) else None,
    }
    return result


async def _upsert_state_row(destination: str, osm_count: int, wiki_count: int) -> None:
    from datetime import datetime, timezone
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is None:
            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=now if osm_count else None,
                wiki_last_ingested_at=now if wiki_count else None,
                request_count=0,
                last_requested_at=None,
            ))
        else:
            if osm_count:
                row.osm_last_ingested_at = now
            if wiki_count:
                row.wiki_last_ingested_at = now
        await db.commit()


def _category_breakdown(destination: str) -> Counter:
    """Read back the freshly-ingested points for this destination and count
    POI categories, to spot-check the round-robin fix actually balanced the
    result (not just that it returned a nonzero count)."""
    from core.qdrant import get_qdrant
    from core.config import settings
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_qdrant()
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    counts: Counter = Counter()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            scroll_filter=dest_filter,
            limit=200,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in points:
            counts[(p.payload or {}).get("poi_type", "unknown")] += 1
        if offset is None:
            break
    return counts


async def main() -> None:
    results: list[dict] = []

    for i, destination in enumerate(DESTINATIONS, 1):
        logger.info("[%d/%d] Re-ingesting %s ...", i, len(DESTINATIONS), destination)
        result = await _reingest_one(destination)
        results.append(result)
        await _upsert_state_row(destination, result["osm_count"], result["wiki_count"])

        breakdown = _category_breakdown(destination)
        top = breakdown.most_common(5)
        logger.info(
            "[%d/%d] %s: %d OSM POIs, %d wiki chunks. Top categories: %s%s",
            i, len(DESTINATIONS), destination, result["osm_count"], result["wiki_count"],
            top, " | errors: osm=%r wiki=%r" % (result["osm_error"], result["wiki_error"])
            if result["osm_error"] or result["wiki_error"] else "",
        )

        if i < len(DESTINATIONS):
            await asyncio.sleep(DELAY_SECONDS)

    logger.info("=== Summary ===")
    for r in results:
        flag = " ⚠️ ZERO DATA" if not r["osm_count"] and not r["wiki_count"] else ""
        logger.info(
            "%s: osm=%d wiki=%d%s", r["destination"], r["osm_count"], r["wiki_count"], flag
        )


if __name__ == "__main__":
    asyncio.run(main())
