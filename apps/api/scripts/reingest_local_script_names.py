"""Re-ingest OSM POIs for destinations stored under local-script names.

scrapers/osm.py read OSM's `name` tag, which holds the name in the *local*
language, so a Kyoto POI was ingested as "清水寺" and a Cairo one in Arabic.
Everything downstream treats a POI name as text an English-speaking traveller
would recognise or type — services/gems.py searches for it inside traveller
comments, services/poi_pinning.py matches it against LLM-proposed names, and
the itinerary renders it to the user. So these destinations were quietly
degraded across the board, not just in hidden gems.

Live audit 2026-07-25 over the real cluster, counting names containing no
Latin letter at all (Turkish/French/Greek-Latin diacritics are handled by
services/name_matching.normalize_name and are *not* the problem here):

    Tokyo 58/60   Taipei 56/60   Seoul 56/60   Athens 54/60   Tbilisi 53/60
    Osaka 53/60   Cairo 50/60    Kyoto 49/60   Bangkok 40/60  Santorini 25/60
    Kathmandu 21/60  Phuket 14/60  Chiang Mai 14/60  Dubai 8/60
    Doha 7/60  Muscat 4/35  Mykonos 6/60

osm.py now prefers `name:en`, then `int_name`, then a Latin fragment
parenthesised inside an otherwise non-Latin name, keeping the local form in
`name_local`. That only affects data at ingestion time, so these destinations
need a real re-fetch — the fix cannot reach already-stored points.

Real writes against the production Qdrant Cloud cluster. OSM only: the
Wikivoyage side of these destinations was never affected. Resumable via a
JSONL state file, in the same shape as scripts/ingest_youtube_full.py, since
Overpass 504s and rate-limits are routine on a run this long.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reingest_local_script_names")

# Overpass rate-limits by convention and gets slower the longer a batch runs;
# 15s matched what previous multi-destination batches needed (see
# scripts/reingest_pilot_batch.py).
DELAY_SECONDS = 15.0

STATE_PATH = Path(__file__).parent / "out" / "reingest_local_script_names.jsonl"

# Ordered worst-affected first, so an interrupted run has still fixed the
# destinations where the problem was near-total.
DESTINATIONS = [
    "Tokyo", "Taipei", "Seoul", "Athens", "Tbilisi", "Osaka", "Cairo",
    "Kyoto", "Bangkok", "Santorini", "Kathmandu", "Phuket", "Chiang Mai",
    "Dubai", "Doha", "Muscat", "Mykonos",
]

_LATIN = re.compile(r"[A-Za-z]")


def _done() -> set[str]:
    if not STATE_PATH.exists():
        return set()
    done = set()
    for line in STATE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("osm_count"):
                done.add(record["destination"])
    return done


def _record(entry: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _latin_share(destination: str) -> tuple[int, int, Counter]:
    """Read back what was actually stored: how many names now carry Latin
    text, and the category mix. Verifying against the cluster rather than the
    run log is the rule this repo already follows for ingestion scripts."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    latin = total = 0
    categories: Counter = Counter()
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
        for point in points:
            payload = point.payload or {}
            name = (payload.get("name") or "").strip()
            if not name:
                continue
            total += 1
            if _LATIN.search(name):
                latin += 1
            categories[payload.get("poi_type", "unknown")] += 1
        if offset is None:
            break
    return latin, total, categories


async def _touch_state_row(destination: str) -> None:
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is not None:
            row.osm_last_ingested_at = datetime.now(UTC)
            await db.commit()


async def main() -> None:
    from scrapers.osm import ingest_osm_pois

    done = _done()
    pending = [d for d in DESTINATIONS if d not in done]
    logger.info("%d destinations, %d already done, %d pending", len(DESTINATIONS), len(done), len(pending))

    for i, destination in enumerate(pending, 1):
        logger.info("[%d/%d] Re-ingesting %s ...", i, len(pending), destination)
        try:
            count = await ingest_osm_pois(destination)
            error = None
        except Exception as exc:  # noqa: BLE001 — one bad destination must not end the batch
            count, error = 0, repr(exc)
            logger.warning("[%d/%d] %s failed: %s", i, len(pending), destination, error)

        latin, total, categories = _latin_share(destination)
        entry = {
            "destination": destination,
            "osm_count": count,
            "latin_names": latin,
            "total_names": total,
            "top_categories": categories.most_common(5),
            "error": error,
            "at": datetime.now(UTC).isoformat(),
        }
        _record(entry)
        logger.info(
            "[%d/%d] %s: %d POIs ingested, %d/%d names now Latin-script. Top: %s",
            i, len(pending), destination, count, latin, total, categories.most_common(4),
        )

        if count:
            await _touch_state_row(destination)
        if i < len(pending):
            await asyncio.sleep(DELAY_SECONDS)

    logger.info("=== Done. State: %s ===", STATE_PATH)


if __name__ == "__main__":
    asyncio.run(main())
