"""Re-ingest every destination's OSM POIs under prominence-ranked selection.

`scrapers/osm.py` used to query Overpass for `node` elements only and rank
nothing, so the 60 slots filled with whatever came back first. Famous
landmarks are mapped as areas — Kiyomizu-dera, Kinkaku-ji and Ginkaku-ji are
`way` elements, Delhi's Jama Masjid a `relation` — so they were structurally
unreachable, not merely out-ranked. Live-measured 2026-07-25 before the fix:

    Kyoto     21 obscure temples + 20 small museums, no Kiyomizu-dera,
              Fushimi Inari, Kinkaku-ji or Arashiyama
    Delhi     7 train stations, no Red Fort, Humayun's Tomb or Chandni Chowk
    Bangkok   12 train stations, no Wat Arun or Wat Pho
    Goa       24 of 60 places of worship, no Fontainhas or Anjuna

Those are exactly the places travellers name in the ingested YouTube/Reddit
comments, which made this the ceiling on hidden gems (services/gems.py can
only match a name that is in the pool) and on itinerary grounding generally.

osm.py now runs a second, prominence-filtered Overpass pass over
nodes+ways+relations and ranks by prominence tier. That only affects data at
ingestion time, so every destination needs a real re-fetch.

Real writes against the production Qdrant Cloud cluster. OSM only — the
Wikivoyage side is untouched. Resumable via a JSONL state file, in the same
shape as scripts/reingest_local_script_names.py, because Overpass 504s and
rate-limits are routine on a run this long and the prominence query is the
heavier of the two.

    cd apps/api && venv/Scripts/python.exe scripts/reingest_prominence_ranking.py

Takes no flags and resumes automatically. Re-run until it reports 0 pending.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reingest_prominence_ranking")

# Two Overpass queries per destination now, and the prominence one is heavy
# (35-45s live for a dense city), so this is more generous than the 15s the
# earlier single-query batches used.
DELAY_SECONDS = 20.0

STATE_PATH = Path(__file__).parent / "out" / "reingest_prominence_ranking.jsonl"

# A destination that comes back with no prominence signal at all is usually a
# failed prominence pass rather than a genuinely unremarkable place — but not
# always (a thinly-mapped rural destination really can have no wikidata-tagged
# POI). So retry it a bounded number of times, then accept the result.
MAX_ATTEMPTS_PER_DESTINATION = 3

# Ordered so an interrupted run has already fixed the destinations the
# problem was measured on, then the item-7 holdover, then everything else.
MEASURED_FIRST = ["Kyoto", "Delhi", "Bangkok", "Goa", "Bengaluru", "Istanbul", "Tokyo"]

# Ingested by an eval fixture, not a real destination.
EXCLUDED = {"Skeleton Test City"}


def _load_state() -> tuple[set[str], Counter]:
    """Returns (destinations that are done, attempts per destination)."""
    done: set[str] = set()
    attempts: Counter = Counter()
    if not STATE_PATH.exists():
        return done, attempts
    for line in STATE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        destination = record["destination"]
        attempts[destination] += 1
        # "Done" means we got POIs *and* a prominence signal — the whole point
        # of the re-ingestion. Falling back to attempt-count stops a
        # legitimately unremarkable destination from being retried forever.
        if record.get("osm_count") and (
            record.get("prominent") or attempts[destination] >= MAX_ATTEMPTS_PER_DESTINATION
        ):
            done.add(destination)
    return done, attempts


def _record(entry: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _all_destinations() -> list[str]:
    """Every destination already present in the osm_pois collection — the
    authoritative set, rather than a hand-maintained list that can drift."""
    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()
    seen: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            limit=1000, with_payload=["destination"], with_vectors=False, offset=offset,
        )
        for point in points:
            destination = (point.payload or {}).get("destination")
            if destination and destination not in EXCLUDED:
                seen.add(destination)
        if offset is None:
            break

    ordered = [d for d in MEASURED_FIRST if d in seen]
    ordered += sorted(seen - set(ordered))
    return ordered


def _readback(destination: str) -> tuple[int, int, Counter, list[str]]:
    """Read what was actually stored, rather than trusting the run log — the
    rule this repo already follows for ingestion scripts."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    total = prominent = 0
    categories: Counter = Counter()
    names: list[str] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_osm,
            scroll_filter=dest_filter, limit=200,
            with_payload=True, with_vectors=False, offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            total += 1
            if payload.get("prominence", 0) > 0:
                prominent += 1
            categories[payload.get("poi_type", "unknown")] += 1
            names.append(payload.get("name", ""))
        if offset is None:
            break
    return total, prominent, categories, names


async def _touch_state_row(destination: str) -> None:
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is not None:
            row.osm_last_ingested_at = datetime.now(UTC)
            await db.commit()


async def main() -> None:
    from core.config import settings
    from scrapers.osm import ingest_osm_pois

    if settings.qdrant_url.startswith(":memory:"):
        logger.error("QDRANT_URL is ':memory:' — this run would persist nothing. Aborting.")
        return

    destinations = _all_destinations()
    done, attempts = _load_state()
    pending = [d for d in destinations if d not in done]
    logger.info(
        "%d destinations, %d already done, %d pending", len(destinations), len(done), len(pending)
    )

    for i, destination in enumerate(pending, 1):
        logger.info("[%d/%d] Re-ingesting %s ...", i, len(pending), destination)
        try:
            count = await ingest_osm_pois(destination)
            error = None
        except Exception as exc:  # noqa: BLE001 — one bad destination must not end the batch
            count, error = 0, repr(exc)
            logger.warning("[%d/%d] %s failed: %s", i, len(pending), destination, error)

        total, prominent, categories, names = _readback(destination)
        top_share = (categories.most_common(1)[0][1] / total) if total else 0.0
        entry = {
            "destination": destination,
            "osm_count": count,
            "stored": total,
            "prominent": prominent,
            "top_category_share": round(top_share, 3),
            "top_categories": categories.most_common(5),
            "names": names,
            "attempt": attempts[destination] + 1,
            "error": error,
            "at": datetime.now(UTC).isoformat(),
        }
        _record(entry)
        logger.info(
            "[%d/%d] %s: %d ingested, %d stored, %d with a prominence signal, "
            "top category share %.2f. Top: %s",
            i, len(pending), destination, count, total, prominent, top_share,
            categories.most_common(4),
        )

        if count:
            await _touch_state_row(destination)
        if i < len(pending):
            await asyncio.sleep(DELAY_SECONDS)

    still_pending = [d for d in destinations if d not in _load_state()[0]]
    logger.info("=== Done. %d still pending. State: %s ===", len(still_pending), STATE_PATH)
    if still_pending:
        logger.info("Re-run to retry: %s", ", ".join(still_pending[:20]))


if __name__ == "__main__":
    asyncio.run(main())
