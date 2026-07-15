"""One-off backfill for destination_ingestion_state (docs/scaling-tech-challenges.md §8).

The new demand-driven scheduler (core/scheduler.py::_refresh_osm_pois) only
refreshes destinations with a row in destination_ingestion_state. Without
this backfill, the curated destinations ingested by the old static-list
scheduler (and the 2026-07-15 retry passes) would silently stop being
refreshed until someone happened to request them again. This writes a row
(request_count=0 — not yet an organic request, just marking existing data as
freshly ingested) for every destination that already has >0 points in the
osm_pois collection and doesn't already have a state row.

Run once, after the OSM retry passes, from apps/api with the venv active.
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_destination_ingestion_state")


def _distinct_osm_destinations() -> set[str]:
    from core.qdrant import get_qdrant
    from core.config import settings

    client = get_qdrant()
    destinations: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            limit=500,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in points:
            dest = (p.payload or {}).get("destination")
            if dest:
                destinations.add(dest)
        if offset is None:
            break
    return destinations


async def main() -> None:
    from datetime import datetime, timezone
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    destinations = _distinct_osm_destinations()
    logger.info("Found %d distinct destinations with OSM data", len(destinations))

    now = datetime.now(timezone.utc)
    created = 0
    async with AsyncSessionLocal() as db:
        for destination in sorted(destinations):
            row = await db.get(DestinationIngestionState, destination)
            if row is not None:
                continue
            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=now,
                wiki_last_ingested_at=None,
                request_count=0,
                last_requested_at=None,
            ))
            created += 1
        await db.commit()

    logger.info("Backfilled %d new destination_ingestion_state rows", created)


if __name__ == "__main__":
    asyncio.run(main())
