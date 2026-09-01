"""One-off full-corpus POI backfill via `scrapers.poi_provider.ingest_pois`
(Google Places during the trial, OSM fallback/after — same policy the live
scheduler uses).

Why this exists: `core/scheduler.py::_refresh_osm_pois` is deliberately
*demand-driven* — it only re-ingests destinations that already have a row in
`destination_ingestion_state`, which is created the first time a real user
requests that destination (`services/destination_ingestion.py`). Destinations
nobody has asked for yet are never touched by the scheduler, Google Places
included. As of 2026-08-31, only 9 of the ~168 `KNOWN_DESTINATIONS` have a
state row, so the Google Places trial has barely been exercised.

This script is a one-time (or occasionally re-run) sweep over the *entire*
`scrapers.reddit.KNOWN_DESTINATIONS` list, calling the same `ingest_pois()`
orchestrator the scheduler uses, so every destination gets a chance to be
served by Google Places (with automatic OSM fallback on failure/empty result,
identical to production behavior) instead of waiting on organic traffic.

Design, reusing patterns already proven in this codebase's other backfill/
reingest scripts (see `backfill_destination_ingestion_state.py` and
`reingest_remaining_backlog.py`):

1. **Skips destinations already ingested "recently" enough** (same
   `settings.osm_refresh_days` staleness window the scheduler itself uses),
   unless `--force` is passed — so re-running this after a partial run (or
   periodically) doesn't burn Google Places quota/cost on data that's
   already fresh.
2. **Chunking with cooldowns + resumable JSONL state** — a ~168-destination
   run is large enough to risk hammering Overpass (for OSM fallbacks) even
   with `scrapers/osm.py`'s existing mirror-rotation/backoff, and Google
   Places calls cost real money past the free cap — a killed/interrupted
   run must not have to start over and re-spend.
3. **Live cost estimate before running** — prints the worst-case cost
   (`settings.google_places_cost_per_1000_calls_usd`, assuming ALL
   destinations go to Google Places, 5 calls each) so a human can sanity
   check before a real run against production.
4. Writes/updates `destination_ingestion_state` per destination (needed so
   the scheduler's weekly refresh picks these up going forward) — reuses
   the same upsert shape as `reingest_remaining_backlog.py`.

Run once, from apps/api with the venv active:
    python scripts/backfill_poi_provider_full_corpus.py [--force] [--fresh] [--dry-run]

Real writes against the production Qdrant Cloud cluster (and Google Places
billing) unless --dry-run is passed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, ".")

from core.logging_config import configure_script_logging  # noqa: E402

# Not logging.basicConfig(): that attaches no filters, so a caught httpx
# exception (whose message carries the full request URL, API key included)
# would land in the console verbatim. See core/logging_config.py.
configure_script_logging()
logger = logging.getLogger("backfill_poi_provider_full_corpus")

CHUNK_SIZE = 10
CHUNK_COOLDOWN_S = 120.0
DELAY_SECONDS = 15.0
DELAY_JITTER_S = 5.0
GOOGLE_PLACES_CALLS_PER_DESTINATION = 5  # landmark/museum_art/nature/entertainment/food_drink

STATE_PATH = "scripts/out/backfill_poi_provider_full_corpus_state.jsonl"


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


async def _already_fresh(destination: str, stale_before: datetime) -> bool:
    """True if destination_ingestion_state already shows a non-stale
    osm_last_ingested_at — matches the scheduler's own staleness check, so
    this script doesn't re-spend Google Places quota on destinations the
    scheduler would already consider fresh."""
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is None or row.osm_last_ingested_at is None:
            return False
        last_ingested = row.osm_last_ingested_at
        if last_ingested.tzinfo is None:
            # sqlite (local dev) stores naive datetimes; Postgres (prod)
            # returns tz-aware ones. Normalize to UTC-aware so this
            # comparison works against either backend.
            last_ingested = last_ingested.replace(tzinfo=UTC)
        return last_ingested >= stale_before


async def _upsert_state_row(destination: str, poi_count: int) -> None:
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is None:
            db.add(DestinationIngestionState(
                destination=destination,
                osm_last_ingested_at=now if poi_count else None,
                wiki_last_ingested_at=None,
                request_count=0,
                last_requested_at=None,
            ))
        else:
            if poi_count:
                row.osm_last_ingested_at = now
        await db.commit()


async def _backfill_one(destination: str) -> dict:
    from scrapers.poi_provider import ingest_pois

    try:
        poi_count, provider_used = await ingest_pois(destination)
        error = None
    except Exception as e:  # a genuinely unreachable destination is skipped,
        # not fatal to the whole run — same contract as _refresh_osm_pois.
        poi_count, provider_used, error = 0, None, str(e)

    return {
        "destination": destination,
        "poi_count": poi_count,
        "provider_used": provider_used,
        "error": error,
        "completed_at": datetime.now(UTC).isoformat(),
    }


async def main() -> None:
    from core.config import settings
    from scrapers.poi_provider import trial_active

    assert settings.qdrant_url and settings.qdrant_url != ":memory:", (
        f"Refusing to run live ingestion against qdrant_url={settings.qdrant_url!r}"
    )
    logger.info("Cluster: %s", settings.qdrant_url[:55])

    force = "--force" in sys.argv
    fresh = "--fresh" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if fresh and os.path.exists(STATE_PATH):
        os.remove(STATE_PATH)
        logger.info("--fresh: removed existing state file %s", STATE_PATH)

    from scrapers.reddit import KNOWN_DESTINATIONS

    logger.info(
        "Google Places trial active today: %s (ends %s)",
        trial_active(), settings.google_places_trial_end_date,
    )
    worst_case_calls = len(KNOWN_DESTINATIONS) * GOOGLE_PLACES_CALLS_PER_DESTINATION
    worst_case_cost = settings.google_places_cost_per_1000_calls_usd * worst_case_calls / 1000
    logger.info(
        "%d destinations x %d calls = %d calls worst-case if ALL go to Google Places "
        "(~$%.2f at $%.2f/1,000 calls, before any free-tier cap) -- actual cost will be "
        "lower for any destination that falls back to OSM.",
        len(KNOWN_DESTINATIONS), GOOGLE_PLACES_CALLS_PER_DESTINATION, worst_case_calls,
        worst_case_cost, settings.google_places_cost_per_1000_calls_usd,
    )

    if dry_run:
        logger.info("--dry-run: exiting before any ingestion or writes.")
        return

    completed = _load_completed()
    stale_before = datetime.now(UTC) - timedelta(days=settings.osm_refresh_days)

    todo: list[str] = []
    skipped_fresh = 0
    for destination in KNOWN_DESTINATIONS:
        if destination in completed:
            continue
        if not force and await _already_fresh(destination, stale_before):
            skipped_fresh += 1
            continue
        todo.append(destination)

    logger.info(
        "%d/%d already recorded in %s, %d already fresh (use --force to re-ingest anyway) "
        "-- %d remaining",
        len(completed), len(KNOWN_DESTINATIONS), STATE_PATH, skipped_fresh, len(todo),
    )

    chunks = [todo[i:i + CHUNK_SIZE] for i in range(0, len(todo), CHUNK_SIZE)]
    results: list[dict] = list(completed.values())
    done_count = len(completed) + skipped_fresh
    total = len(KNOWN_DESTINATIONS)

    google_places_count = 0
    osm_count = 0
    error_count = 0

    for chunk_idx, chunk in enumerate(chunks, 1):
        logger.info("=== Chunk %d/%d (%d destinations) ===", chunk_idx, len(chunks), len(chunk))
        for destination in chunk:
            done_count += 1
            logger.info("[%d/%d] Backfilling %s ...", done_count, total, destination)
            result = await _backfill_one(destination)

            try:
                await _upsert_state_row(destination, result["poi_count"])
            except Exception as e:
                # Scheduler-freshness bookkeeping only -- must never block or
                # discard the real Qdrant ingestion writes above.
                logger.warning("Could not upsert destination_ingestion_state for %r: %s", destination, e)

            if result["error"]:
                error_count += 1
                logger.warning("[%d/%d] %s: FAILED -- %s", done_count, total, destination, result["error"])
            else:
                if result["provider_used"] == "google_places":
                    google_places_count += 1
                else:
                    osm_count += 1
                logger.info(
                    "[%d/%d] %s: %d POIs via %s",
                    done_count, total, destination, result["poi_count"], result["provider_used"],
                )

            results.append(result)
            _append_state(result)

            is_last_in_chunk = destination == chunk[-1]
            is_last_overall = destination == todo[-1] if todo else True
            if not is_last_overall and not is_last_in_chunk:
                await asyncio.sleep(DELAY_SECONDS + random.uniform(0, DELAY_JITTER_S))

        if chunk_idx < len(chunks):
            logger.info(
                "Chunk %d/%d done -- cooling down %.0fs before next chunk",
                chunk_idx, len(chunks), CHUNK_COOLDOWN_S,
            )
            await asyncio.sleep(CHUNK_COOLDOWN_S)

    logger.info("=== Summary ===")
    logger.info(
        "google_places=%d osm=%d errors=%d (this run only; %d skipped as already-fresh)",
        google_places_count, osm_count, error_count, skipped_fresh,
    )

    os.makedirs("scripts/out", exist_ok=True)
    out_path = f"scripts/out/backfill_poi_provider_full_corpus_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("Wrote summary: %s", out_path)


if __name__ == "__main__":
    asyncio.run(main())
