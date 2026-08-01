"""First full `visa_info` ingestion across the seed country list (issue #59,
follow-up to #37 / commit `bf70000`).

The collection and the retrieval path shipped in v10.52.0, but no ingestion
run has ever been performed, so `visa_info` is empty. With an empty collection
`services/visa.py::retrieve_visa_note()` correctly returns "" and the wizard
says nothing -- a silent no-op rather than a visible failure, which is exactly
why this needs an explicit run rather than waiting to be noticed.

Not waiting for the scheduler: `visa_info_refresh` runs on an
`IntervalTrigger(days=settings.visa_info_refresh_days)` and APScheduler
schedules the FIRST fire at now+interval, so a fresh deploy ingests nothing
for 30 days.

Iterates countries, not destinations -- visa rules are country-level (see
scrapers/visa_info.py for the measurement behind that), so `destination` on a
stored point holds a country name here, not a city.

Cost: none. This is the free Wikimedia `action=parse` API, one article per
country, no key and no metered quota -- unlike the YouTube backfill this is
paced for politeness only (Wikimedia asks for unhurried serial access), not
for a budget.

Reuses ingest_visa_info(), which already carries the fetch retry/backoff and
the delete-then-upsert stale-point cleanup. That cleanup matters more here
than for other sources: an obsolete visa rule is worse than a missing one.

Resumable: one JSON line per country is appended to STATE_PATH as it
completes, so a killed run can be restarted without redoing finished work.
Pass --fresh to start over.

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
from pathlib import Path

sys.path.insert(0, ".")

from core.logging_config import configure_script_logging  # noqa: E402

# Not logging.basicConfig(): that attaches no filters, so a caught exception
# whose message carries a request URL would land in the console verbatim.
# See core/logging_config.py.
configure_script_logging()
logger = logging.getLogger("ingest_visa_info_full")

# Wikimedia asks for unhurried serial access. The scheduler's own loop uses
# 1.0s; this run is a one-off burst over the whole seed list rather than a
# background trickle, so it goes slower, with jitter so the request train
# isn't perfectly periodic.
DELAY_SECONDS = 2.0
DELAY_JITTER_S = 1.0

STATE_PATH = "scripts/out/ingest_visa_info_full_state.jsonl"
SUMMARY_PATH = "scripts/out/ingest_visa_info_full_summary.json"

# Same rationale and shape as scripts/ingest_youtube_full.py: retry a country
# that produced nothing a bounded number of times, then accept the result.
# See _load_done().
MAX_ATTEMPTS_PER_COUNTRY = 3


def _load_done(fresh: bool) -> dict[str, dict]:
    """Countries needing no further work, keyed to their last record.

    "Done" means chunks were actually ingested. A recorded failure or an empty
    result stays *pending*, so a transient Wikimedia error is retried rather
    than written off as a recorded-but-empty success -- the failure shape that
    has bitten this project repeatedly (a run log full of clean-looking zeroes).
    The attempt cap stops a country whose article has no entry section from
    being refetched on every future run forever.
    """
    path = Path(STATE_PATH)
    if fresh and path.exists():
        path.unlink()
        logger.info("--fresh: removed existing state file %s", STATE_PATH)
    if not path.exists():
        return {}

    attempts: dict[str, int] = {}
    last: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        country = row["country"]
        attempts[country] = attempts.get(country, 0) + 1
        last[country] = row

    done: dict[str, dict] = {}
    for country, row in last.items():
        if row.get("chunks") or attempts[country] >= MAX_ATTEMPTS_PER_COUNTRY:
            done[country] = row
    return done


def _append_state(row: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


async def main() -> None:
    from core.config import settings
    from scrapers.visa_info import VISA_SEED_COUNTRIES, ingest_visa_info

    assert settings.qdrant_url and settings.qdrant_url != ":memory:", (
        f"Refusing to run live ingestion against qdrant_url={settings.qdrant_url!r}"
    )
    logger.info("Cluster: %s", settings.qdrant_url[:55])
    logger.info("Collection: %s", settings.qdrant_collection_visa_info)

    done = _load_done("--fresh" in sys.argv)
    pending = [c for c in VISA_SEED_COUNTRIES if c not in done]
    logger.info(
        "%d seed countries, %d already done in a prior run, %d pending.",
        len(VISA_SEED_COUNTRIES), len(done), len(pending),
    )

    results: list[dict] = list(done.values())

    for i, country in enumerate(pending, 1):
        row: dict = {"country": country, "at": datetime.now(UTC).isoformat()}
        try:
            chunks = await ingest_visa_info(country)
            row["chunks"] = chunks
            row["error"] = None
        except Exception as e:
            # Per-country failure is non-fatal: one unreachable article must
            # not cost the other sixty, the same contract _refresh_visa_info()
            # holds in core/scheduler.py.
            row["chunks"] = 0
            row["error"] = f"{type(e).__name__}: {e}"
            logger.warning("visa_info %r failed: %s", country, row["error"])

        if row["chunks"]:
            logger.info("[%d/%d] %s: %d chunks", i, len(pending), country, row["chunks"])
        else:
            # WARNING, not INFO: a zero here is either a fetch failure or an
            # article with no entry rules, and both need a human to look.
            logger.warning(
                "[%d/%d] %s: NO chunks -- stays pending", i, len(pending), country,
            )

        results.append(row)
        _append_state(row)

        if i < len(pending):
            await asyncio.sleep(DELAY_SECONDS + random.uniform(0, DELAY_JITTER_S))

    total = sum(r["chunks"] for r in results)
    zero = sorted(r["country"] for r in results if not r["chunks"])
    remaining = len(VISA_SEED_COUNTRIES) - len(_load_done(False))

    logger.info("=== Summary ===")
    logger.info(
        "%d chunks across %d/%d countries. Zero-chunk (%d): %s",
        total, len(VISA_SEED_COUNTRIES) - len(zero), len(VISA_SEED_COUNTRIES),
        len(zero), zero,
    )
    logger.info("Still pending after this run: %d", remaining)

    Path(SUMMARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(SUMMARY_PATH).write_text(
        json.dumps(
            {
                "at": datetime.now(UTC).isoformat(),
                "total_chunks": total,
                "countries": len(VISA_SEED_COUNTRIES),
                "zero_chunk": zero,
                "remaining": remaining,
                "results": sorted(results, key=lambda r: r["country"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Wrote summary: %s", SUMMARY_PATH)


if __name__ == "__main__":
    asyncio.run(main())
