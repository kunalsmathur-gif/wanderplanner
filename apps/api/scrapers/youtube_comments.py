"""YouTube video discovery + comment ingester (docs/NEXT_SESSION_TODO.md item 3).

Hidden-gems alternative sentiment source while Reddit ingestion stays
blocked on API approval (see services/gems.py, scrapers/reddit.py).
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
    destination. 10,000 units/day quota ceiling means ~100 destination
    searches/day if nothing else uses quota that day.
  - `commentThreads.list` (1 unit/call) — top-level comments for a
    discovered video, cheap enough to not meaningfully compete for quota.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
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


def _search_query(destination: str) -> str:
    # "hidden places" / "things to do" phrasing surfaces India's large
    # domestic-vlog ecosystem better than a bare destination name search
    # (docs/NEXT_SESSION_TODO.md item 3's "India domestic-travel coverage
    # findings" — generic English queries under-serve domestic content).
    return f"{destination} travel guide hidden places things to do"


async def search_travel_videos(destination: str) -> list[dict[str, str]]:
    """Discover up to `settings.youtube_videos_per_destination` relevant
    video IDs for a destination via `search.list`. Returns `[]` (not an
    exception) when no API key is configured, so callers can treat "no key"
    and "no results" the same way — best-effort by design, same as every
    other ingestion source in this codebase."""
    if not settings.youtube_api_key:
        logger.info("YOUTUBE_API_KEY not set — skipping video discovery for %r", destination)
        return []

    params = {
        "key": settings.youtube_api_key,
        "part": "snippet",
        "q": _search_query(destination),
        "type": "video",
        "maxResults": settings.youtube_videos_per_destination,
        "relevanceLanguage": "en",
        "safeSearch": "moderate",
    }

    data: dict[str, Any] | None = None
    for attempt in range(1, _MAX_FETCH_ATTEMPTS + 1):
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{_API_BASE}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == _MAX_FETCH_ATTEMPTS:
                    logger.warning(
                        "YouTube search.list failed for %r after %d attempts: %s", destination, attempt, e
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

    params = {
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
                        "YouTube commentThreads.list failed for %r after %d attempts: %s", video_id, attempt, e
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
