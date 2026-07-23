"""Re-ingest the final completeness-gate stragglers + three silently
mis-geocoded destinations (NEXT_SESSION_TODO.md item 1 continuation).

A 2026-07-23 live read-only audit of all 168 KNOWN_DESTINATIONS found only
10 still failing the gate (down from the ~95 of the prior backlog batch) and,
via a geocode spot-check of the *passing* set, three destinations that pass
the count-only gate while holding data for the WRONG same-named city:

  - Austin   -> was Austin, NEVADA (a ~150-person ghost town, 3 OSM POIs)
               instead of Austin, Texas.
  - La Paz   -> was La Paz, MEXICO (Baja California Sur) instead of the
               Bolivian seat of government the catalog groups it with.
  - Valencia -> was Valencia, VENEZUELA instead of Valencia, Spain.

All three are now pinned in services/geocode.py::GEOCODE_QUERY_OVERRIDES
(same-name collisions the generic Wikipedia country cross-check can't
resolve — Austin is a same-country namesake; La Paz/Valencia are real cities
of comparable prominence to the intended one). Because their existing 60-POI
datasets are for the wrong city, this script WIPES their osm/wiki points
first (delete_stale_destination_points with an empty keep-set) so the OSM
data-loss guard in ingest_osm_pois() can't fall back to the wrong data if a
fresh fetch comes back transiently thin.

The remaining stragglers are correctly geocoded; they just trip the
category-dominance (>50% single tag) or thin-OSM (<20) checks and are re-run
to let the adaptive radius-expansion + round-robin selection rebalance them.
Small pilgrimage/temple towns may legitimately stay temple-dominated — that
is real-world skew, not a bug, and is reported as such.

Real writes against the production Qdrant Cloud cluster.

Run from apps/api:
    PYTHONUTF8=1 PYTHONPATH=. ./venv/Scripts/python.exe -m scripts.reingest_geocode_fixes_and_stragglers
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reingest_geocode_fixes_and_stragglers")

DELAY_SECONDS = 15.0
DELAY_JITTER_S = 5.0

# Wrong-city data must be wiped before re-ingest (see module docstring).
GEOCODE_FIXED = ["Austin", "La Paz", "Valencia"]
# Correctly geocoded, just category-dominated or thin — plain re-ingest.
STRAGGLERS = [
    "Paris", "Sri Lanka", "Dharamshala", "Pushkar", "Alleppey", "Varkala",
    "Khajuraho", "Mahabaleshwar", "Lonavala",
]
ALL = GEOCODE_FIXED + STRAGGLERS


def _wipe_wrong_city(destination: str) -> None:
    """Delete ALL existing osm/wiki points for a destination whose stored data
    is for the wrong same-named city, so a fresh (correct-city) ingest starts
    from a clean slate and the ingest_osm_pois data-loss guard has nothing
    stale to fall back to."""
    from core.qdrant import delete_stale_destination_points, get_qdrant
    from core.config import settings

    client = get_qdrant()
    for coll in (settings.qdrant_collection_osm, settings.qdrant_collection_wiki):
        deleted = delete_stale_destination_points(client, coll, destination, set())
        logger.info("Wiped %d wrong-city points from %s for %r", deleted, coll, destination)


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
        "completed_at": datetime.now(timezone.utc).isoformat(),
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
    for i, destination in enumerate(ALL, 1):
        if destination in GEOCODE_FIXED:
            try:
                _wipe_wrong_city(destination)
            except Exception as e:
                logger.warning("Could not wipe wrong-city data for %r: %s", destination, e)

        logger.info("[%d/%d] Re-ingesting %s ...", i, len(ALL), destination)
        result = await _reingest_one(destination)
        try:
            await _upsert_state_row(destination, result["osm_count"], result["wiki_count"])
        except Exception as e:
            # Scheduler-freshness bookkeeping only — must never block or discard
            # the real Qdrant ingestion writes above.
            logger.warning("Could not upsert destination_ingestion_state for %r: %s", destination, e)

        breakdown: Counter = Counter()
        try:
            breakdown = _category_breakdown(destination)
        except Exception as e:
            logger.warning("Could not fetch category breakdown for %r: %s", destination, e)
        result["top_categories"] = breakdown.most_common(5)
        total = sum(breakdown.values())
        top_share = (breakdown.most_common(1)[0][1] / total) if total else 0.0
        result["top_share"] = round(top_share, 2)

        logger.info(
            "[%d/%d] %s: %d OSM POIs (top %.0f%%), %d wiki chunks. Top: %s%s",
            i, len(ALL), destination, result["osm_count"], top_share * 100,
            result["wiki_count"], result["top_categories"],
            (" | errors: osm=%r wiki=%r" % (result["osm_error"], result["wiki_error"]))
            if result["osm_error"] or result["wiki_error"] else "",
        )
        results.append(result)

        if i < len(ALL):
            await asyncio.sleep(DELAY_SECONDS + random.uniform(0, DELAY_JITTER_S))

    logger.info("=== Summary ===")
    for r in results:
        logger.info("%s: osm=%d (top %.0f%%) wiki=%d", r["destination"], r["osm_count"],
                    r.get("top_share", 0) * 100, r["wiki_count"])

    os.makedirs("scripts/out", exist_ok=True)
    out_path = f"scripts/out/reingest_geocode_fixes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("Wrote summary: %s", out_path)


if __name__ == "__main__":
    asyncio.run(main())
