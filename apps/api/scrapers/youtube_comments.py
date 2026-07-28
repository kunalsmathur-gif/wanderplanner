"""YouTube video discovery + comment ingester (docs/NEXT_SESSION_TODO.md item 3).

Hidden-gems sentiment source. This replaced Reddit rather than standing in
for it: Reddit was dropped as a planned source on 2026-07-26 after its OAuth
app review never issued credentials (see services/gems.py, scrapers/reddit.py
— that collection is frozen, still read, never written).
YouTube travel-vlog comments are structurally identical to Reddit posts for
this purpose — a place mention plus surrounding sentiment, at real volume —
so this reuses services/gems.py's existing lexicon/mention-counting logic
via the shared `youtube_comments` Qdrant collection rather than inventing a
new scoring path.

Requires a free, self-serve `YOUTUBE_API_KEY` (YouTube Data API v3 — no
approval process, unlike Reddit's OAuth app-review gate). Every function
here is a documented no-op when the key is unset, same pattern as
core/config.py's `pexels_api_key`.

Two API calls, both free-tier:
  - `search.list` (100 units/query) — discovers relevant travel videos for a
    destination. ⚠️ The 10,000-units/day allowance is NOT the ceiling that
    binds here: `search.list` has its own dedicated cap of 100 calls per
    project per day (`defaultSearchListPerDayPerProject`), a separate meter,
    resetting at midnight Pacific. Measured off a live 429 body 2026-07-26;
    see TECHNICAL_DOCUMENTATION §14 v10.40.1. `_search_budget_available()`
    below meters against that cap, not against units.
  - `commentThreads.list` (1 unit/call) — top-level comments for a
    discovered video. It draws on the unit allowance only, so it never
    competes with discovery for the cap above.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from core.config import settings
from core.embeddings import embed
from core.qdrant import delete_stale_destination_points, get_qdrant

logger = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com/youtube/v3"

# Same rationale as scrapers/osm.py / scrapers/wikivoyage.py — transient
# failures shouldn't silently record a destination as having zero data.
_MAX_FETCH_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0

# Rolling-24h search budget (see settings.youtube_daily_search_budget).
# `search.list` costs 100 of the free tier's 10,000 daily units, so the two
# *automatic* callers — the cold-start gate (services/destination_ingestion.py,
# itself capped at 5 cold starts/hour = up to 120/day) and the scheduler
# refresh loop — could between them exhaust the day's quota and leave manual
# re-ingestion or eval runs unable to search at all. This is a process-global
# window, the same shape and for the same reason as
# destination_ingestion.py's `_cold_start_budget_available()`: cheap, no new
# infra, and it degrades to "no videos found" (which every caller already
# handles) rather than an error.
_daily_search_window = timedelta(hours=24)
_search_times: deque[datetime] = deque()
_search_budget_guard = asyncio.Lock()


async def _search_budget_available() -> bool:
    """Reserve one of the rolling day's `search.list` slots, or return False
    if the budget is exhausted."""
    async with _search_budget_guard:
        now = datetime.now(UTC)
        cutoff = now - _daily_search_window
        while _search_times and _search_times[0] < cutoff:
            _search_times.popleft()
        if len(_search_times) >= settings.youtube_daily_search_budget:
            return False
        _search_times.append(now)
        return True


def reset_search_budget() -> None:
    """Clear the rolling search-budget window. Test hook — production code
    never needs this (the window self-expires)."""
    _search_times.clear()


def _search_query(destination: str) -> str:
    # "hidden places" / "things to do" phrasing surfaces India's large
    # domestic-vlog ecosystem better than a bare destination name search
    # (docs/NEXT_SESSION_TODO.md item 3's "India domestic-travel coverage
    # findings" — generic English queries under-serve domestic content).
    return f"{destination} travel guide hidden places things to do"


async def search_travel_videos(
    destination: str, query: str | None = None, max_results: int | None = None
) -> list[dict[str, str]]:
    """Discover up to `settings.youtube_videos_per_destination` relevant
    video IDs for a destination via `search.list`. Returns `[]` (not an
    exception) when no API key is configured or the rolling-24h search
    budget is exhausted, so callers can treat "no key", "over budget" and
    "no results" the same way — best-effort by design, same as every other
    ingestion source in this codebase.

    `query` overrides the default hidden-gems-flavoured search phrasing —
    scrapers/itinerary_corpus.py passes an itinerary-shaped query
    ("3 day X itinerary travel vlog") because it's looking for trip-plan
    videos to extract day structure from, not comment sentiment."""
    if not settings.youtube_api_key:
        logger.info("YOUTUBE_API_KEY not set — skipping video discovery for %r", destination)
        return []

    if not await _search_budget_available():
        logger.warning(
            "YouTube search budget exhausted (%d searches/24h) — skipping video discovery for %r",
            settings.youtube_daily_search_budget,
            destination,
        )
        return []

    params: dict[str, str | int] = {
        "key": settings.youtube_api_key,
        "part": "snippet",
        "q": query or _search_query(destination),
        "type": "video",
        "maxResults": max_results or settings.youtube_videos_per_destination,
        "relevanceLanguage": "en",
        "safeSearch": "moderate",
    }

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{_API_BASE}/search", params=params)
                if resp.status_code in (403, 429):
                    # Quota exhaustion is terminal for the rest of the quota day,
                    # not a transient blip: retrying spends 3 calls against a
                    # 100/day `search.list` cap and cannot succeed on any of
                    # them. `fetch_video_comments` below already applies this
                    # rule to 403; search had no equivalent, which is how one
                    # exhausted day turned into 141 wasted calls.
                    logger.warning(
                        "YouTube search.list refused for %r (HTTP %d — quota or rate limit); "
                        "not retrying", destination, resp.status_code,
                    )
                    return []
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    # `e` is deliberately not interpolated: httpx embeds the
                    # full request URL -- API key included -- in
                    # HTTPStatusError's message.
                    logger.warning(
                        "YouTube search.list failed for %r after %d attempts: %s",
                        destination, attempt, type(e).__name__,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    videos = []
    for item in (data or {}).get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        title = (item.get("snippet") or {}).get("title")
        if video_id and title:
            videos.append({"video_id": video_id, "title": title})
    return videos


async def fetch_video_comments(video_id: str) -> list[dict[str, Any]]:
    """Fetch top-level comments for one video via `commentThreads.list`.
    Returns `[]` on no key, disabled comments, or any request failure —
    never raises, matching every other scraper's best-effort contract."""
    if not settings.youtube_api_key:
        return []

    params: dict[str, str | int] = {
        "key": settings.youtube_api_key,
        "part": "snippet",
        "videoId": video_id,
        "maxResults": settings.youtube_comments_per_video,
        "textFormat": "plainText",
        "order": "relevance",
    }

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{_API_BASE}/commentThreads", params=params)
                if resp.status_code == 403:
                    # Comments disabled on this specific video is a normal,
                    # expected outcome (not a transient failure) — don't
                    # burn retries on it.
                    logger.info("Comments disabled or forbidden for video %r", video_id)
                    return []
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "YouTube commentThreads.list failed for %r after %d attempts: %s",
                        video_id, attempt, type(e).__name__,
                    )
                    return []
                await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)

    comments = []
    for item in (data or {}).get("items", []):
        top = (
            (item.get("snippet") or {})
            .get("topLevelComment", {})
            .get("snippet", {})
        )
        text = top.get("textDisplay", "")
        if len(text.strip()) >= 20:  # skip near-empty/emoji-only comments
            comments.append({
                "text": text.strip(),
                "comment_id": (item.get("snippet") or {}).get("topLevelComment", {}).get("id", ""),
                "like_count": top.get("likeCount", 0),
            })
    return comments


async def ingest_youtube_comments(destination: str) -> int:
    """Discover travel videos for `destination`, fetch their comments, and
    upsert into the `youtube_comments` Qdrant collection. Returns the number
    of comments ingested (0 if no API key configured). Safe to re-run —
    delete-then-upsert per destination, same as scrapers/osm.py /
    scrapers/wikivoyage.py."""
    if not settings.youtube_api_key:
        return 0

    videos = await search_travel_videos(destination)
    if not videos:
        return 0

    docs: list[dict[str, Any]] = []
    for video in videos:
        comments = await fetch_video_comments(video["video_id"])
        for c in comments:
            docs.append({
                "destination": destination,
                "source": "youtube_comment",
                "video_id": video["video_id"],
                "video_title": video["title"],
                "text": c["text"],
                "like_count": c["like_count"],
                "source_url": f"https://www.youtube.com/watch?v={video['video_id']}&lc={c['comment_id']}",
            })

    if not docs:
        return 0

    texts = [d["text"] for d in docs]
    # Offload the CPU-bound embed() call — same rule as every other
    # ingestion source (scrapers/osm.py, scrapers/wikivoyage.py,
    # scrapers/reddit.py): this must never block the event loop.
    vectors = await asyncio.to_thread(embed, texts)

    from qdrant_client.models import PointStruct

    points = []
    new_ids: set[int] = set()
    for doc, vec in zip(docs, vectors):
        point_id = hashlib.md5(f"{doc['video_id']}::{doc['text'][:50]}".encode()).hexdigest()
        point_id_int = int(point_id, 16) % (2**63)
        new_ids.add(point_id_int)
        points.append(PointStruct(id=point_id_int, vector=vec, payload=doc))

    client = get_qdrant()
    stale_count = delete_stale_destination_points(
        client, settings.qdrant_collection_youtube_comments, destination, new_ids
    )
    if stale_count:
        logger.info("Deleted %d stale YouTube comment points for %r before re-ingestion", stale_count, destination)
    client.upsert(collection_name=settings.qdrant_collection_youtube_comments, points=points)
    return len(points)
