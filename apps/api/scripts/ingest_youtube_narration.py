"""Ingest YouTube narration (transcripts + descriptions) for every destination.

`docs/NEXT_SESSION_TODO.md` §C. Comments were measured as the wrong medium for
price grounding — 1-3 money-shaped chunks per destination, and
`food_per_day_estimate_inr` returning None everywhere. Vloggers state costs
out loud and descriptions carry explicit breakdowns, so this ingests narration
into the `youtube_narration` collection (see scrapers/youtube_narration.py for
why it is deliberately separate from `youtube_comments`).

**This run is cheap by construction.** Video discovery reads IDs already stored
by the comment backfill rather than calling `search.list`, so the 100
calls/project/day cap that binds every other YouTube path here is untouched.
Descriptions cost 1 unit per 50 videos. Transcripts need no key at all.

    cd apps/api && venv/Scripts/python.exe scripts/ingest_youtube_narration.py

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

from core.logging_config import configure_script_logging  # noqa: E402

# Not logging.basicConfig(): that attaches no filters, so a caught httpx
# exception (whose message carries the full request URL, API key included)
# would land in the console verbatim. See core/logging_config.py.
configure_script_logging()
logger = logging.getLogger("ingest_youtube_narration")

STATE_PATH = Path(__file__).parent / "out" / "ingest_youtube_narration.jsonl"

# Transcript fetches are unmetered but not free of politeness obligations —
# this hits YouTube's public timedtext endpoint once per video.
DELAY_SECONDS = 5.0

# Same idiom as reingest_prominence_ranking.py: "done" means real data landed,
# with a bounded retry so a destination whose videos genuinely have no English
# captions and no descriptions can't be retried forever.
MAX_ATTEMPTS_PER_DESTINATION = 3


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
        if record.get("stored") or attempts[destination] >= MAX_ATTEMPTS_PER_DESTINATION:
            done.add(destination)
    return done, attempts


def _record(entry: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _destinations_with_videos() -> list[str]:
    """Destinations that already have ingested comments — narration discovery
    reads video IDs from those payloads, so anything else has nothing to do."""
    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()
    seen: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_youtube_comments,
            limit=1000, with_payload=["destination"], with_vectors=False, offset=offset,
        )
        for point in points:
            destination = (point.payload or {}).get("destination")
            if destination:
                seen.add(destination)
        if offset is None:
            break
    return sorted(seen)


def _readback(destination: str) -> tuple[int, Counter]:
    """Read what actually landed, rather than trusting the return value — the
    rule this repo already follows for ingestion scripts."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    from core.config import settings
    from core.qdrant import get_qdrant

    client = get_qdrant()
    dest_filter = Filter(must=[FieldCondition(key="destination", match=MatchValue(value=destination))])
    total = 0
    by_source: Counter = Counter()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_youtube_narration,
            scroll_filter=dest_filter, limit=200,
            with_payload=["source"], with_vectors=False, offset=offset,
        )
        for point in points:
            total += 1
            by_source[(point.payload or {}).get("source", "unknown")] += 1
        if offset is None:
            break
    return total, by_source


async def main() -> None:
    from core.config import settings
    from scrapers.youtube_narration import ingest_youtube_narration

    if settings.qdrant_url.startswith(":memory:"):
        logger.error("QDRANT_URL is ':memory:' — this run would persist nothing. Aborting.")
        return

    destinations = _destinations_with_videos()
    done, attempts = _load_state()
    pending = [d for d in destinations if d not in done]
    logger.info(
        "%d destinations with videos, %d already done, %d pending",
        len(destinations), len(done), len(pending),
    )

    for i, destination in enumerate(pending, 1):
        logger.info("[%d/%d] Ingesting narration for %s ...", i, len(pending), destination)
        try:
            count = await ingest_youtube_narration(destination)
            error = None
        except Exception as exc:  # noqa: BLE001 — one bad destination must not end the batch
            count, error = 0, repr(exc)
            logger.warning("[%d/%d] %s failed: %s", i, len(pending), destination, type(exc).__name__)

        total, by_source = _readback(destination)
        _record({
            "destination": destination,
            "ingested": count,
            "stored": total,
            "by_source": dict(by_source),
            "attempt": attempts[destination] + 1,
            # redact(): a state file is a non-log sink, so the RedactionFilter
            # never sees it (the v10.40.3 lesson).
            "error": _redact(error),
            "at": datetime.now(UTC).isoformat(),
        })
        if total:
            logger.info(
                "[%d/%d] %s: %d chunks stored (%s)",
                i, len(pending), destination, total, dict(by_source),
            )
        else:
            logger.warning(
                "[%d/%d] %s: NO narration stored — stays pending", i, len(pending), destination
            )

        if i < len(pending):
            await asyncio.sleep(DELAY_SECONDS)

    still_pending = [d for d in destinations if d not in _load_state()[0]]
    logger.info("=== Done. %d still pending. State: %s ===", len(still_pending), STATE_PATH)
    if still_pending:
        logger.info("Re-run to retry: %s", ", ".join(still_pending[:20]))


def _redact(text: str | None) -> str | None:
    if not text:
        return text
    from core.logging_config import redact

    return redact(text)


if __name__ == "__main__":
    asyncio.run(main())
