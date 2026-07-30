"""YouTube narration ingester — transcripts + video descriptions.

`docs/NEXT_SESSION_TODO.md` §C. Measured 2026-07-26: comments are the wrong
medium for price grounding. Across every ingested destination there were only
1-3 money-shaped chunks in `youtube_comments`, and `food_per_day_estimate_inr`
returned None for all eight destinations spot-checked. People do not quote
prices in comments — but vloggers state costs out loud ("this thali was 150
rupees", "the room came to about 2000 a night"), and descriptions frequently
carry an explicit cost breakdown. That is narration, not audience reaction, and
it is a different corpus.

**Why a separate collection rather than adding to `youtube_comments`:**
`services/gems.py` scores hidden gems by *mention count* — a place named in 4
comments is gem signal, one named in 400 is a crowd favourite. That arithmetic
assumes one mention ≈ one independent person. A transcript violates it: a
vlogger says "Hawa Mahal" eight times in a single video and it is still one
voice. Merging narration into `youtube_comments` would silently inflate mention
counts and misclassify gems as crowd favourites. So narration lands in its own
collection, is wired into the *price* path (`core/cost_grounding.py`), and is
deliberately NOT wired into gems.

**Quota: this source is nearly free, which is the point.**
  - Video *discovery* costs nothing. The completed comment backfill (v10.40.2,
    170/170 destinations) already stored a `video_id` on every point, so the
    videos for a destination are read back out of Qdrant rather than
    re-discovered. No `search.list` call is made here at all — the 100/day
    project cap (v10.40.1) is untouched.
  - Transcripts cost nothing. `youtube_transcript_api` reads the public
    timedtext endpoint and needs no API key.
  - Descriptions cost 1 unit per `videos.list` call against the 10,000/day
    unit budget, and up to 50 video IDs batch into one call — so a full
    170-destination run is roughly 20 units, versus the 17,000 it would cost
    if discovery went through `search.list` again.

Best-effort throughout, like every other scraper here: no key, no captions, or
a failed request all degrade to "no docs" rather than raising.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any

import httpx

from core.config import settings
from core.embeddings import embed
from core.ingestion_metadata import build_ingestion_payload
from core.qdrant import delete_stale_destination_points, get_qdrant

logger = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com/youtube/v3"

# `videos.list` accepts up to 50 ids per request (YouTube Data API v3 limit).
_VIDEOS_LIST_BATCH = 50

# Transcripts run 10-20k chars. ~500 matches the Wikivoyage chunk size so
# retrieval behaves consistently across collections.
_CHUNK_CHARS = 500

# Auto-generated captions arrive as one unpunctuated run of text, so a chunk
# boundary can fall between an amount and the thing it paid for ("...it cost
# 450 | rupees for the whole thali"). core/price_extraction.py scopes an
# amount's context to its own sentence, widening to +/-90 chars — so chunks
# overlap by a little more than that widen window, ensuring any amount near a
# boundary still has its context intact in one of the two chunks.
_CHUNK_OVERLAP_CHARS = 120

# A single long vlog shouldn't dominate a destination's corpus.
_MAX_CHUNKS_PER_VIDEO = 40

# Scroll bound when reading known video IDs back out of youtube_comments.
_VIDEO_SCAN_LIMIT = 500

# English first, then Hindi. Live-measured 2026-07-27 on Jaipur: most Indian
# destination vlogs carry NO English caption track and only a Hindi
# auto-generated one, so requesting ("en",) alone — as the itinerary-corpus
# path does — silently discards the domestic narration this India-first
# product most needs. `youtube_transcript_api` returns the first available
# track in list order, so English is still preferred where it exists.
#
# Safe here specifically because the price path is lexical, not semantic:
# core/cost_grounding.py::_scroll_price_candidates_sync finds amounts with a
# regex over stored text, so a Devanagari chunk containing "₹500" matches on
# the digits regardless of how poorly an English-centric embedding model
# represents the surrounding words. Do NOT assume the same holds for any
# future semantic-search consumer of this collection.
_TRANSCRIPT_LANGUAGES = ("en", "hi")


def _narration_chunks(text: str, max_chars: int = _CHUNK_CHARS) -> list[str]:
    """Split narration into ~`max_chars` chunks, tolerating unpunctuated text.

    `scrapers/wikivoyage.py::_sentence_boundary_chunks` splits on sentence
    punctuation alone, which is right for prose but degenerates on
    auto-generated captions: YouTube's ASR emits no full stops at all, so the
    whole transcript is one "sentence" and the function returns it as a single
    chunk. Here an oversized piece is hard-wrapped at word boundaries with an
    overlap, so no amount loses the words around it.
    """
    pieces: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        # Unpunctuated run: wrap on whitespace, keeping an overlap tail.
        words = sentence.split()
        current: list[str] = []
        length = 0
        for word in words:
            if length + len(word) + 1 > max_chars and current:
                pieces.append(" ".join(current))
                # Re-seed the next piece with the tail of this one.
                tail: list[str] = []
                tail_len = 0
                for w in reversed(current):
                    if tail_len + len(w) + 1 > _CHUNK_OVERLAP_CHARS:
                        break
                    tail.insert(0, w)
                    tail_len += len(w) + 1
                current = tail
                length = tail_len
            current.append(word)
            length += len(word) + 1
        if current:
            pieces.append(" ".join(current))

    # Merge short adjacent pieces up to the target size.
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if len(buf) + len(piece) + 1 > max_chars and buf:
            chunks.append(buf.strip())
            buf = piece
        else:
            buf = (buf + " " + piece).strip()
    if buf:
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) > 80]


def known_video_ids_sync(destination: str) -> list[dict[str, str]]:
    """Video IDs already discovered for `destination`, read out of the
    `youtube_comments` collection. Zero API cost — this is what makes the whole
    source cheap (see module docstring)."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = get_qdrant()
    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )
    seen: dict[str, str] = {}
    offset = None
    scanned = 0
    while scanned < _VIDEO_SCAN_LIMIT:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_youtube_comments,
            scroll_filter=dest_filter,
            limit=200,
            with_payload=["video_id", "video_title"],
            with_vectors=False,
            offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            video_id = payload.get("video_id")
            if video_id and video_id not in seen:
                seen[video_id] = payload.get("video_title", "")
        scanned += len(points)
        if offset is None:
            break
    return [{"video_id": vid, "title": title} for vid, title in seen.items()]


async def fetch_video_descriptions(video_ids: list[str]) -> dict[str, str]:
    """Descriptions for up to 50 video IDs per `videos.list` call (1 unit each).

    Deliberately a different endpoint from `search.list`: this does not touch
    the 100-calls/project/day search cap that binds every other YouTube path
    here. Returns `{}` on no key or any failure.
    """
    if not settings.youtube_api_key or not video_ids:
        return {}

    descriptions: dict[str, str] = {}
    for start in range(0, len(video_ids), _VIDEOS_LIST_BATCH):
        batch = video_ids[start : start + _VIDEOS_LIST_BATCH]
        params = {
            "key": settings.youtube_api_key,
            "part": "snippet",
            "id": ",".join(batch),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{_API_BASE}/videos", params=params)
                if resp.status_code in (403, 429):
                    # Same rule as search.list (v10.40.3): a quota/permission
                    # refusal is terminal for the day, not a transient blip.
                    logger.warning(
                        "YouTube videos.list refused (HTTP %d — quota or permission); "
                        "skipping descriptions", resp.status_code,
                    )
                    return descriptions
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            # `e` is never interpolated: httpx embeds the full request URL,
            # API key included, in HTTPStatusError's message (v10.40.3).
            logger.warning(
                "YouTube videos.list failed for a batch of %d: %s", len(batch), type(e).__name__
            )
            continue

        for item in data.get("items", []):
            snippet = item.get("snippet") or {}
            description = (snippet.get("description") or "").strip()
            if description:
                descriptions[item.get("id", "")] = description
    return descriptions


async def _transcript_text(video_id: str, title: str) -> str:
    """Transcript text for one video, or "" if it has no English captions.

    `scrapers/itinerary_corpus.py::fetch_youtube_transcript` is declared
    `async` but performs blocking network I/O with no awaits inside it —
    `youtube_transcript_api` is a synchronous client. Awaiting it directly
    would stall the event loop for the length of the fetch, which matters
    because the scheduler shares a process with the API server (the same rule
    `embed()` follows; see docs/system-design.md's async-correctness note).
    Driving the coroutine on a worker thread keeps the loop free while still
    reusing that function rather than duplicating its parsing.
    """
    from scrapers.itinerary_corpus import fetch_youtube_transcript

    def _fetch() -> dict[str, Any] | None:
        # New event loop, private to this worker thread.
        return asyncio.run(
            fetch_youtube_transcript(video_id, title, languages=_TRANSCRIPT_LANGUAGES)
        )

    try:
        doc = await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.warning("Transcript fetch failed for %r: %s", video_id, type(e).__name__)
        return ""
    return (doc or {}).get("raw_text", "") or ""


async def ingest_youtube_narration(destination: str) -> int:
    """Ingest transcripts + descriptions for `destination`'s known videos into
    the `youtube_narration` collection. Returns the number of chunks stored.

    Safe to re-run — delete-then-upsert per destination, same contract as
    `scrapers/osm.py` and `scrapers/youtube_comments.py`.
    """
    videos = await asyncio.to_thread(known_video_ids_sync, destination)
    if not videos:
        logger.info(
            "%r: no known videos in youtube_comments — run the comment ingester first", destination
        )
        return 0

    video_ids = [v["video_id"] for v in videos]
    descriptions = await fetch_video_descriptions(video_ids)

    docs: list[dict[str, Any]] = []
    for video in videos:
        video_id = video["video_id"]
        title = video.get("title", "")
        url = f"https://www.youtube.com/watch?v={video_id}"

        description = descriptions.get(video_id, "")
        if description:
            for chunk in _narration_chunks(description):
                docs.append(build_ingestion_payload(
                    destination=destination,
                    source="youtube_description",
                    text=chunk,
                    source_url=url,
                    source_name="YouTube",
                    extra={"video_id": video_id, "video_title": title},
                ))

        transcript = await _transcript_text(video_id, title)
        if transcript:
            for chunk in _narration_chunks(transcript)[:_MAX_CHUNKS_PER_VIDEO]:
                docs.append(build_ingestion_payload(
                    destination=destination,
                    source="youtube_transcript",
                    text=chunk,
                    source_url=url,
                    source_name="YouTube",
                    extra={"video_id": video_id, "video_title": title},
                ))

    if not docs:
        logger.info("%r: %d videos known but no transcripts or descriptions", destination, len(videos))
        return 0

    texts = [d["text"] for d in docs]
    vectors = await asyncio.to_thread(embed, texts)

    from qdrant_client.models import PointStruct

    points = []
    new_ids: set[int] = set()
    for doc, vec in zip(docs, vectors):
        digest = hashlib.md5(
            f"{doc['video_id']}::{doc['source']}::{doc['text'][:50]}".encode()
        ).hexdigest()
        point_id = int(digest, 16) % (2**63)
        new_ids.add(point_id)
        points.append(PointStruct(id=point_id, vector=vec, payload=doc))

    client = get_qdrant()
    stale = delete_stale_destination_points(
        client, settings.qdrant_collection_youtube_narration, destination, new_ids
    )
    if stale:
        logger.info("Deleted %d stale narration points for %r before re-ingestion", stale, destination)
    client.upsert(collection_name=settings.qdrant_collection_youtube_narration, points=points)

    n_desc = sum(1 for d in docs if d["source"] == "youtube_description")
    logger.info(
        "%r: stored %d narration chunks (%d description, %d transcript) from %d videos",
        destination, len(points), n_desc, len(points) - n_desc, len(videos),
    )
    return len(points)


async def destinations_missing_transcripts() -> list[str]:
    """Destinations whose stored `youtube_narration` points are
    description-only — i.e. every transcript fetch failed for that
    destination's videos.

    In practice this almost always means a YouTube transcript-endpoint IP
    block hit mid-run (observed 2026-07-30: a 172-destination backfill burst
    got blocked after ~70 destinations, and even a single retry burst
    re-triggered the block within 2-3 destinations). Descriptions still
    landed via the separate, unrelated `videos.list` path, so these
    destinations are NOT "no docs" — they're specifically missing the
    higher-value transcript source. Used by the scheduler's slow drip-retry
    job (`core/scheduler.py::_retry_youtube_narration_transcripts`) rather
    than the one-time full-backfill script
    (`scripts/ingest_youtube_narration.py`), since retrying transcripts is
    free but must be done in a small trickle, not a full-corpus burst, to
    avoid re-triggering the same block.
    """
    client = get_qdrant()
    has_transcript: set[str] = set()
    has_narration: set[str] = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection_youtube_narration,
            limit=500, with_payload=["destination", "source"], with_vectors=False, offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            destination = payload.get("destination")
            if not destination:
                continue
            has_narration.add(destination)
            if payload.get("source") == "youtube_transcript":
                has_transcript.add(destination)
        if offset is None:
            break
    return sorted(has_narration - has_transcript)
