"""Full-corpus Wikivoyage re-ingestion to pick up district sub-articles
(issue #58, follow-up to #45 / commit `785312d`).

`scrapers/wikivoyage.py` now discovers and fetches a hub city's district
sub-articles (e.g. "Paris/11th arrondissement") up to
`settings.wikivoyage_max_district_subpages` (default 8, live-measured gains:
Paris 156->377 chunks, Bangkok 143->680, Tokyo 94->293, Delhi 64->312), but
that's an ingestion-time change only -- nothing is live on the Qdrant
cluster until every destination is re-ingested through `ingest_wikivoyage()`.

Wikivoyage-only (unlike scripts/reingest_remaining_backlog.py, which also
re-ingests OSM): non-hub destinations cost zero additional fetches over a
normal Wikivoyage re-ingest, so a full-corpus pass is safe, but hub cities
now cost up to 8 extra article fetches + embeddings each, so this still
chunks with cooldowns and must not run alongside another ingestion batch
(per the issue's explicit warning).

Reuses ingest_wikivoyage() (retry/backoff + district discovery + politeness
delay + delete-then-upsert stale-point cleanup already built in).

Real writes against the production Qdrant Cloud cluster.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from datetime import UTC, datetime

sys.path.insert(0, ".")

from core.logging_config import configure_script_logging  # noqa: E402

# Not logging.basicConfig(): that attaches no filters, so a caught httpx
# exception (whose message carries the full request URL, API key included)
# would land in the console verbatim. See core/logging_config.py.
configure_script_logging()
logger = logging.getLogger("reingest_wikivoyage_districts")

CHUNK_SIZE = 15
CHUNK_COOLDOWN_S = 90.0
DELAY_SECONDS = 8.0
DELAY_JITTER_S = 4.0

STATE_PATH = "scripts/out/reingest_wikivoyage_districts_state.jsonl"


def _load_completed() -> dict[str, dict]:
    completed: dict[str, dict] = {}
    if not os.path.exists(STATE_PATH):
        return completed
    with open(STATE_PATH, encoding="utf-8") as f:
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
    from scrapers.wikivoyage import ingest_wikivoyage

    try:
        wiki_count = await ingest_wikivoyage(destination)
        wiki_error = None
    except Exception as e:
        wiki_count = 0
        wiki_error = str(e)
    return {
        "destination": destination,
        "wiki_count": wiki_count,
        "wiki_error": wiki_error,
        "completed_at": datetime.now(UTC).isoformat(),
    }


async def _upsert_state_row(destination: str, wiki_count: int) -> None:
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is None:
            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=None,
                wiki_last_ingested_at=now if wiki_count else None,
                request_count=0,
                last_requested_at=None,
            ))
        elif wiki_count:
            row.wiki_last_ingested_at = now
        await db.commit()


async def main() -> None:
    from core.config import settings
    from scrapers.reddit import KNOWN_DESTINATIONS

    assert settings.qdrant_url and settings.qdrant_url != ":memory:", (
        f"Refusing to run live ingestion against qdrant_url={settings.qdrant_url!r}"
    )
    logger.info("Cluster: %s", settings.qdrant_url[:55])
    logger.info("wikivoyage_max_district_subpages=%s", settings.wikivoyage_max_district_subpages)

    fresh = "--fresh" in sys.argv
    if fresh and os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
        logger.info("--fresh: removed existing state file %s", STATE_PATH)

    destinations = list(KNOWN_DESTINATIONS)
    completed = _load_completed()
    todo = [d for d in destinations if d not in completed]
    logger.info(
        "%d/%d destinations already recorded in %s -- resuming with %d remaining",
        len(completed), len(destinations), STATE_PATH, len(todo),
    )

    chunk_list = [todo[i:i + CHUNK_SIZE] for i in range(0, len(todo), CHUNK_SIZE)]
    results: list[dict] = list(completed.values())
    done_count = len(completed)

    for chunk_idx, chunk in enumerate(chunk_list, 1):
        logger.info("=== Chunk %d/%d (%d destinations) ===", chunk_idx, len(chunk_list), len(chunk))
        for destination in chunk:
            done_count += 1
            logger.info("[%d/%d] Re-ingesting %s ...", done_count, len(destinations), destination)
            result = await _reingest_one(destination)
            try:
                await _upsert_state_row(destination, result["wiki_count"])
            except Exception as e:
                # Scheduler-freshness bookkeeping only -- must never block or
                # discard the real Qdrant ingestion write above.
                logger.warning("Could not upsert destination_ingestion_state for %r: %s", destination, e)

            logger.info(
                "[%d/%d] %s: %d wiki chunks%s",
                done_count, len(destinations), destination, result["wiki_count"],
                f" | error: {result['wiki_error']!r}" if result["wiki_error"] else "",
            )
            results.append(result)
            _append_state(result)

            is_last_in_chunk = destination == chunk[-1]
            is_last_overall = done_count == len(destinations)
            if not is_last_overall and not is_last_in_chunk:
                await asyncio.sleep(DELAY_SECONDS + random.uniform(0, DELAY_JITTER_S))

        if chunk_idx < len(chunk_list):
            logger.info("Chunk %d/%d done -- cooling down %.0fs before next chunk", chunk_idx, len(chunk_list), CHUNK_COOLDOWN_S)
            await asyncio.sleep(CHUNK_COOLDOWN_S)

    logger.info("=== Summary ===")
    zero = [r["destination"] for r in results if not r["wiki_count"]]
    for r in results:
        flag = " ** ZERO DATA" if not r["wiki_count"] else ""
        logger.info("%s: wiki=%d%s", r["destination"], r["wiki_count"], flag)
    logger.info("Zero-data destinations (%d): %s", len(zero), zero)

    os.makedirs("scripts/out", exist_ok=True)
    out_path = f"scripts/out/reingest_wikivoyage_districts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("Wrote summary: %s", out_path)


if __name__ == "__main__":
    asyncio.run(main())
