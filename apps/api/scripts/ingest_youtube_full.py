"""Full YouTube comment ingestion across every tracked destination.

Background: `YOUTUBE_API_KEY` was never set on Railway until 2026-07-25, so
the `youtube_comments` collection only ever held the single destination
(Jaipur) used to live-verify the scraper on 2026-07-21. Neither automatic
caller could have filled it in: the cold-start gate only fires on a
first-ever request for a destination, and `_refresh_youtube_comments` uses
an `IntervalTrigger` with no `start_date`, so its first fire is 14 days
after boot. This script does the one-time backfill those two paths would
otherwise take months to cover.

Ordering deliberately mirrors `core/scheduler.py::_refresh_youtube_comments`
-- NULL `youtube_last_ingested_at` first, then `request_count` DESC -- so if
the quota runs out partway, it ran out on the least-demanded destinations.

Quota is the real constraint, not politeness. `search.list` costs 100 of the
free tier's 10,000 daily units, but the *binding* limit is a separate
per-endpoint cap — `defaultSearchListPerDayPerProject`, 100 calls per project
per day — and every destination needs exactly one, so a day's ceiling is 100
destinations no matter how long the script runs. It stops cleanly at
`settings.youtube_daily_search_budget` and reports what is left for a
follow-up run tomorrow. Note the quota resets at **midnight Pacific**: a run
started at 08:00 UTC is still on the previous quota day.

Real writes against the production Qdrant Cloud cluster -- the same cluster
Railway reads from, so ingested comments are live for prod immediately.
Note the reverse is not true for Postgres: this stamps
`youtube_last_ingested_at` in whatever DB `DATABASE_URL` points at (locally,
dev.db), not prod's, since prod's Postgres is only reachable on Railway's
private network. Harmless -- prod's scheduler may re-ingest a destination
once more later, and ingestion is delete-then-upsert idempotent.

Resumable: one JSON line per destination is appended to STATE_PATH as it
completes, so a killed run can be restarted without redoing (or re-charging
quota for) work that already finished. Pass --fresh to start over.
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
# The app's own logging (core/logging_config.py) redacts `AIza…` keys from
# every record, but a standalone script using basicConfig gets no such filter
# — and httpx logs full request URLs at INFO, which for YouTube means the API
# key in the query string lands in the console/CI log verbatim. Nothing here
# needs httpx's per-request chatter, so drop it below INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("ingest_youtube_full")

DELAY_SECONDS = 2.0
STATE_PATH = "scripts/out/ingest_youtube_full_state.jsonl"
SUMMARY_PATH = "scripts/out/ingest_youtube_full_summary.json"

# Same rationale and shape as scripts/reingest_prominence_ranking.py: retry a
# destination that produced nothing a bounded number of times, then accept the
# result. See _load_done().
MAX_ATTEMPTS_PER_DESTINATION = 3


def _load_done(fresh: bool) -> dict[str, dict]:
    """Destinations needing no further work, keyed to their last record.

    "Done" means comments were actually ingested. A recorded failure or an
    empty result stays *pending* — the same rule the scheduler follows by
    leaving `youtube_last_ingested_at` NULL, so a transient search failure is
    retried rather than written off as a recorded-but-empty success. Falling
    back to attempt count stops a destination nobody has vlogged about from
    spending a `search.list` call on every future run forever.
    """
    path = Path(STATE_PATH)
    if fresh or not path.exists():
        return {}
    done: dict[str, dict] = {}
    attempts: Counter = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        destination = row["destination"]
        attempts[destination] += 1
        if row.get("comments") or attempts[destination] >= MAX_ATTEMPTS_PER_DESTINATION:
            done[destination] = row
    return done


def _record(row: dict) -> None:
    path = Path(STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


async def _destinations() -> list[str]:
    """Every tracked destination, in the scheduler's own priority order."""
    from sqlalchemy import select

    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DestinationIngestionState.destination).order_by(
                DestinationIngestionState.youtube_last_ingested_at.is_(None).desc(),
                DestinationIngestionState.request_count.desc(),
                DestinationIngestionState.destination,
            )
        )
        return [row[0] for row in result.all()]


async def _stamp_ingested(destination: str, when: datetime) -> None:
    from db import AsyncSessionLocal
    from db_models import DestinationIngestionState

    async with AsyncSessionLocal() as db:
        row = await db.get(DestinationIngestionState, destination)
        if row is not None:
            row.youtube_last_ingested_at = when
            await db.commit()


async def main() -> None:
    from core.config import settings
    from scrapers import youtube_comments as yt

    assert settings.qdrant_url and settings.qdrant_url != ":memory:", (
        f"Refusing to run live ingestion against qdrant_url={settings.qdrant_url!r} "
        "-- nothing would persist. Point QDRANT_URL at the real cluster first."
    )
    assert settings.youtube_api_key, "YOUTUBE_API_KEY is not set -- nothing to do."

    fresh = "--fresh" in sys.argv
    done = _load_done(fresh)
    destinations = await _destinations()
    pending = [d for d in destinations if d not in done]

    budget = settings.youtube_daily_search_budget
    logger.info(
        "%d destinations tracked, %d already done in a prior run, %d pending. "
        "Daily search budget: %d (1 search.list per destination = 100 units each).",
        len(destinations), len(done), len(pending), budget,
    )

    results: list[dict] = []
    stopped_on_budget = False

    for i, destination in enumerate(pending, 1):
        if len(yt._search_times) >= budget:
            logger.warning(
                "Rolling 24h search budget exhausted (%d searches). Stopping with %d "
                "destinations left -- re-run tomorrow to continue.",
                budget, len(pending) - i + 1,
            )
            stopped_on_budget = True
            break

        now = datetime.now(UTC)
        row: dict = {"destination": destination, "at": now.isoformat()}
        try:
            count = await yt.ingest_youtube_comments(destination)
            row["comments"] = count
        except Exception as e:
            row["comments"] = 0
            row["error"] = f"{type(e).__name__}: {e}"
            logger.warning("[%d/%d] %s FAILED: %s", i, len(pending), destination, e)
            _record(row)
            results.append(row)
            continue

        if count:
            await _stamp_ingested(destination, now)
        else:
            # Over budget, no videos found, or comments disabled everywhere.
            # Same rule as the scheduler: leave the timestamp NULL so this is a
            # retryable no-op, never a recorded-but-empty success.
            row["retryable_no_op"] = True

        if count:
            logger.info("[%d/%d] %s: %d comments ingested", i, len(pending), destination, count)
        else:
            # Not a success. Said plainly, because "0 comments ingested" reads
            # like one in a run log and hid 47 consecutive quota failures once.
            logger.warning("[%d/%d] %s: NO comments — stays pending", i, len(pending), destination)
        _record(row)
        results.append(row)
        await asyncio.sleep(DELAY_SECONDS)

    ingested = [r for r in results if r.get("comments")]
    empty = [r for r in results if not r.get("comments") and not r.get("error")]
    failed = [r for r in results if r.get("error")]

    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "tracked": len(destinations),
        "already_done_before_run": len(done),
        "attempted": len(results),
        "ingested": len(ingested),
        "total_comments": sum(r["comments"] for r in ingested),
        "empty_retryable": len(empty),
        "failed": len(failed),
        "searches_used": len(yt._search_times),
        "stopped_on_budget": stopped_on_budget,
        # Re-read state so this applies the same done-rule the next run will:
        # anything that failed or came back empty is still pending, not done.
        "remaining": len(destinations) - len(_load_done(False)),
    }
    Path(SUMMARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(SUMMARY_PATH).write_text(json.dumps(summary | {"results": results}, indent=2), encoding="utf-8")

    logger.info("=== Summary ===")
    for key, value in summary.items():
        logger.info("  %s: %s", key, value)
    if empty:
        logger.info("  empty (will retry next run): %s", ", ".join(r["destination"] for r in empty))
    if failed:
        logger.info("  failed: %s", ", ".join(r["destination"] for r in failed))


if __name__ == "__main__":
    asyncio.run(main())
