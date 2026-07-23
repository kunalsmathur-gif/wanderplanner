"""India tier-2/3 re-ingestion batch (NEXT_SESSION_TODO.md item 2).

Targets the 34 India tier-2/3 towns / hill-stations / heritage & beach
circuits that the 2026-07-22 India seed-list expansion added to
scrapers/reddit.py::KNOWN_DESTINATIONS but which have **zero** OSM *and*
zero wiki data in the production Qdrant cluster (confirmed via a read-only
audit 2026-07-23). India is the core user cohort, and these low-traffic
towns are far less likely than the popular metros to hit Overpass rate
limits, so they're the highest value / lowest risk first batch.

Re-ingests both OSM POIs and Wikivoyage text via the existing
ingest_osm_pois()/ingest_wikivoyage() (retry/backoff + delete-then-upsert
stale-point cleanup already built in), upserts a destination_ingestion_state
row so the scheduler keeps them fresh, and writes a JSON summary to
scripts/out/ for post-run verification.

Real writes against the production Qdrant Cloud cluster.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reingest_india_tier23")

# Low-traffic towns tolerate a shorter delay than the metros, but keep a
# conservative gap so a burst across 34 destinations doesn't trip Overpass.
DELAY_SECONDS = 12.0

DESTINATIONS = [
    # Himalayas / north
    "Rishikesh", "Haridwar", "Manali", "Shimla", "Leh", "Ladakh",
    "Dharamshala", "Nainital", "Mussoorie", "Srinagar", "Amritsar", "Spiti",
    # Rajasthan
    "Udaipur", "Jodhpur", "Jaisalmer", "Pushkar",
    # South
    "Pondicherry", "Munnar", "Alleppey", "Ooty", "Coorg", "Mysuru",
    "Hampi", "Gokarna", "Varkala",
    # East / northeast
    "Darjeeling", "Gangtok", "Shillong",
    # Central / west
    "Khajuraho", "Aurangabad", "Mahabaleshwar", "Lonavala",
    # Islands
    "Andaman", "Port Blair",
]


async def _reingest_one(destination: str) -> dict:
    from scrapers.osm import ingest_osm_pois
    from scrapers.wikivoyage import ingest_wikivoyage

    osm_count, wiki_count = await asyncio.gather(
        ingest_osm_pois(destination),
        ingest_wikivoyage(destination),
        return_exceptions=True,
    )
    return {
        "destination": destination,
        "osm_count": osm_count if isinstance(osm_count, int) else 0,
        "wiki_count": wiki_count if isinstance(wiki_count, int) else 0,
        "osm_error": str(osm_count) if isinstance(osm_count, Exception) else None,
        "wiki_error": str(wiki_count) if isinstance(wiki_count, Exception) else None,
    }


async def _upsert_state_row(destination: str, osm_count: int, wiki_count: int) -> None:
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
    from core.config import settings

    assert settings.qdrant_url and settings.qdrant_url != ":memory:", (
        f"Refusing to run live ingestion against qdrant_url={settings.qdrant_url!r}"
    )
    logger.info("Cluster: %s", settings.qdrant_url[:55])

    results: list[dict] = []
    for i, destination in enumerate(DESTINATIONS, 1):
        logger.info("[%d/%d] Re-ingesting %s ...", i, len(DESTINATIONS), destination)
        result = await _reingest_one(destination)
        await _upsert_state_row(destination, result["osm_count"], result["wiki_count"])

        breakdown = _category_breakdown(destination)
        result["top_categories"] = breakdown.most_common(5)
        logger.info(
            "[%d/%d] %s: %d OSM POIs, %d wiki chunks. Top: %s%s",
            i, len(DESTINATIONS), destination, result["osm_count"], result["wiki_count"],
            result["top_categories"],
            (" | errors: osm=%r wiki=%r" % (result["osm_error"], result["wiki_error"]))
            if result["osm_error"] or result["wiki_error"] else "",
        )
        results.append(result)
        if i < len(DESTINATIONS):
            await asyncio.sleep(DELAY_SECONDS)

    logger.info("=== Summary ===")
    zero = []
    for r in results:
        flag = " ** ZERO DATA" if not r["osm_count"] and not r["wiki_count"] else ""
        if flag:
            zero.append(r["destination"])
        logger.info("%s: osm=%d wiki=%d%s", r["destination"], r["osm_count"], r["wiki_count"], flag)
    logger.info("Zero-data destinations (%d): %s", len(zero), zero)

    os.makedirs("scripts/out", exist_ok=True)
    out_path = f"scripts/out/reingest_india_tier23_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("Wrote summary: %s", out_path)


if __name__ == "__main__":
    asyncio.run(main())
