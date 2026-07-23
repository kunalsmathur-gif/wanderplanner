"""Remaining international/backlog re-ingestion batch (NEXT_SESSION_TODO.md
item 2, continuation of scripts/reingest_intl_osm_zero_holdovers.py).

Targets the 95 KNOWN_DESTINATIONS that a 2026-07-23 live completeness audit
found still failing the gate (`eval/data_completeness_scoring.py` --
MIN_OSM_POIS=20, MIN_WIKI_CHUNKS=1, MAX_CATEGORY_SHARE=0.5). Almost all have
`wiki_chunk_count=0` (Wikivoyage was never ingested for these) with OSM
already at ~50-60 POIs from an earlier pre-round-robin-fix ingestion pass,
several also still category-dominated.

Unlike the smaller prior batches, this one is large enough to risk
saturating Overpass on its own even with the 2026-07-23 mirror-rotation +
exponential-backoff fix in scrapers/osm.py, so this script adds two more
guardrails on top:

1. **Chunking with cooldowns** -- processes CHUNK_SIZE destinations, then
   sleeps CHUNK_COOLDOWN_S before the next chunk, so a long run doesn't
   hammer Overpass continuously for 30-90+ minutes straight.
2. **Resumable state** -- writes one line of JSON per destination to
   STATE_PATH as it completes (not just a single summary at the end). If the
   script is killed/fails partway through, re-running it skips any
   destination already recorded as attempted in STATE_PATH instead of
   re-doing (and re-rate-limiting) work that already finished. Delete or
   pass --fresh to start over.

Reuses the existing ingest_osm_pois()/ingest_wikivoyage() (retry/backoff +
mirror rotation + delete-then-upsert stale-point cleanup + adaptive radius
expansion all already built in).

Real writes against the production Qdrant Cloud cluster.
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
logger = logging.getLogger("reingest_remaining_backlog")

# Each chunk's destinations still get an inter-destination delay (with
# jitter); the cooldown below is *additionally* inserted between chunks so
# Overpass gets a real breather during a long run, not just a brief pause.
CHUNK_SIZE = 10
CHUNK_COOLDOWN_S = 120.0
DELAY_SECONDS = 15.0
DELAY_JITTER_S = 5.0

STATE_PATH = "scripts/out/reingest_remaining_backlog_state.jsonl"

# The 95 destinations from the 2026-07-23 live completeness audit of all
# KNOWN_DESTINATIONS not already fixed in this or the prior two sessions'
# batches (India tier-2/3, 9 POC-magnet cities, 7 OSM-zero holdovers).
DESTINATIONS = [
    "Osaka", "Bangkok", "Bali", "Seoul", "Hong Kong", "Taipei", "Kuala Lumpur",
    "Hanoi", "Hoi An", "Chiang Mai", "Siem Reap", "Kathmandu", "Goa", "Kolkata",
    "Chennai", "Hyderabad", "Sri Lanka", "Colombo", "Doha", "Muscat",
    "Cappadocia", "Tbilisi", "Baku", "Paris", "Budapest", "Lisbon", "Porto",
    "Madrid", "Athens", "Mykonos", "Dubrovnik", "Split", "Copenhagen",
    "Stockholm", "Helsinki", "Edinburgh", "Dublin", "Bruges", "Florence",
    "Milan", "Zurich", "Geneva", "Brussels", "Tallinn", "Riga", "Vilnius",
    "Krakow", "Munich", "Hamburg", "Seville", "Valencia", "Nice", "Lyon",
    "Marseille", "Cinque Terre", "Los Angeles", "San Francisco", "Chicago",
    "Miami", "Las Vegas", "New Orleans", "Boston", "Denver", "Austin",
    "Washington DC", "Cancun", "Tulum", "Oaxaca", "Havana", "Bogotá",
    "Cartagena", "Lima", "Cusco", "Machu Picchu", "Buenos Aires",
    "Rio de Janeiro", "São Paulo", "Santiago", "Montevideo", "La Paz",
    "Toronto", "Montreal", "Quebec City", "Cape Town", "Marrakech", "Cairo",
    "Nairobi", "Zanzibar", "Sydney", "Melbourne", "Brisbane", "Auckland",
    "Queenstown", "Bora Bora", "Honolulu",
]


def _load_completed() -> dict[str, dict]:
    completed: dict[str, dict] = {}
    if not os.path.exists(STATE_PATH):
        return completed
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            completed[row["destination"]] = row
    return completed


def _append_state(row: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


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

    fresh = "--fresh" in sys.argv
    if fresh and os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
        logger.info("--fresh: removed existing state file %s", STATE_PATH)

    completed = _load_completed()
    todo = [d for d in DESTINATIONS if d not in completed]
    logger.info(
        "%d/%d destinations already recorded in %s -- resuming with %d remaining",
        len(completed), len(DESTINATIONS), STATE_PATH, len(todo),
    )

    chunks = [todo[i:i + CHUNK_SIZE] for i in range(0, len(todo), CHUNK_SIZE)]
    results: list[dict] = list(completed.values())
    done_count = len(completed)

    for chunk_idx, chunk in enumerate(chunks, 1):
        logger.info("=== Chunk %d/%d (%d destinations) ===", chunk_idx, len(chunks), len(chunk))
        for destination in chunk:
            done_count += 1
            logger.info("[%d/%d] Re-ingesting %s ...", done_count, len(DESTINATIONS), destination)
            result = await _reingest_one(destination)
            try:
                await _upsert_state_row(destination, result["osm_count"], result["wiki_count"])
            except Exception as e:
                # Scheduler-freshness bookkeeping only -- must never block or
                # discard the real Qdrant ingestion writes above.
                logger.warning("Could not upsert destination_ingestion_state for %r: %s", destination, e)

            breakdown = Counter()
            try:
                breakdown = _category_breakdown(destination)
            except Exception as e:
                logger.warning("Could not fetch category breakdown for %r: %s", destination, e)
            result["top_categories"] = breakdown.most_common(5)

            logger.info(
                "[%d/%d] %s: %d OSM POIs, %d wiki chunks. Top: %s%s",
                done_count, len(DESTINATIONS), destination, result["osm_count"], result["wiki_count"],
                result["top_categories"],
                (" | errors: osm=%r wiki=%r" % (result["osm_error"], result["wiki_error"]))
                if result["osm_error"] or result["wiki_error"] else "",
            )
            results.append(result)
            _append_state(result)

            is_last_in_chunk = destination == chunk[-1]
            is_last_overall = done_count == len(DESTINATIONS)
            if not is_last_overall and not is_last_in_chunk:
                await asyncio.sleep(DELAY_SECONDS + random.uniform(0, DELAY_JITTER_S))

        if chunk_idx < len(chunks):
            logger.info("Chunk %d/%d done -- cooling down %.0fs before next chunk", chunk_idx, len(chunks), CHUNK_COOLDOWN_S)
            await asyncio.sleep(CHUNK_COOLDOWN_S)

    logger.info("=== Summary ===")
    zero = []
    for r in results:
        flag = " ** ZERO DATA" if not r["osm_count"] and not r["wiki_count"] else ""
        if flag:
            zero.append(r["destination"])
        logger.info("%s: osm=%d wiki=%d%s", r["destination"], r["osm_count"], r["wiki_count"], flag)
    logger.info("Zero-data destinations (%d): %s", len(zero), zero)

    os.makedirs("scripts/out", exist_ok=True)
    out_path = f"scripts/out/reingest_remaining_backlog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("Wrote summary: %s", out_path)


if __name__ == "__main__":
    asyncio.run(main())
