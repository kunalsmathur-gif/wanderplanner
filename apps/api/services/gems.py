"""Hidden-gem scoring service (docs/GTM_STRATEGY.md §2, product bet 1).

Ranks OSM-verified POIs for a destination by community signal blended from
every configured sentiment source — `reddit` and `youtube_comments` Qdrant
collections, each contributing chunks with per-source provenance
(docs/NEXT_SESSION_TODO.md item 3: YouTube added as an alternative source
while Reddit ingestion stays blocked on API approval): **high sentiment ×
low mention volume = hidden gem**, high mention volume = crowd favourite. Generic LLMs
regurgitate top-10 lists; this surfaces the place praised in 4 comments over
the one appearing in 400 — with provenance ("mentioned in N traveller posts
on r/x") so the recommendation is checkable, not vibes.

Every gem candidate comes from the `osm_pois` collection, so a hallucinated
place can never be recommended — if OSM doesn't know it, we don't rank it.

Scale / latency / concurrency / cost design:
- **Zero LLM calls, zero external APIs, zero new infra** — deterministic
  lexicon math over collections we already ingest on a schedule.
- **No per-request corpus scans**: scores are computed at most once per
  destination per `_CACHE_TTL_SECONDS` (24h) and served from an in-process
  cache. The corpus itself only changes on scheduled re-ingestion, so a
  24h TTL loses nothing.
- **Bounded compute**: scrolls are capped (`_MAX_POIS` × `_MAX_CHUNKS`);
  worst case is a few hundred ms of pure-CPU string scanning, run via
  `asyncio.to_thread` so the event loop never blocks (same rule as
  embed()/rerank_scores(), see docs/itinerary-generation-flow.md v10.13).
- **Stampede-safe**: a per-destination asyncio.Lock means N concurrent
  first requests for the same city compute once, not N times.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time

from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.config import settings
from core.qdrant import get_qdrant

logger = logging.getLogger(__name__)

# Bounded-compute caps. 300 POIs × 800 chunks ≈ 240k substring checks —
# hundreds of ms of CPU at the very worst, once per destination per day.
_MAX_POIS = 300
_MAX_CHUNKS = 800
_CACHE_TTL_SECONDS = 24 * 3600

# Classification thresholds (tunable without redeploy via future settings if
# needed — kept module-level constants until real-traffic data says otherwise).
_GEM_MAX_MENTIONS = 6        # more mentions than this = too well-known to be a "gem"
_CROWD_MIN_MENTIONS = 12     # this many mentions = crowd favourite
_GEM_MIN_SENTIMENT = 0.55    # Laplace-smoothed positive ratio floor for gems
_SENTIMENT_WINDOW = 120      # chars of context around a mention scanned for sentiment
_MAX_GEMS = 10
_MAX_CROWD_FAVOURITES = 8

# Small hand-authored lexicons — deliberately not ML. Deterministic, free,
# and auditable; upgrade path is a real sentiment model iff eval data shows
# the lexicon misclassifying.
_POSITIVE_WORDS = frozenset({
    "amazing", "authentic", "beautiful", "best", "calm", "charming", "favourite",
    "favorite", "gem", "gorgeous", "highlight", "incredible", "local", "lovely",
    "loved", "magical", "peaceful", "perfect", "quiet", "recommend", "serene",
    "stunning", "underrated", "unique", "worth",
    # Romanized Hindi/Hinglish supplement (docs/NEXT_SESSION_TODO.md item 3:
    # domestic-travel YouTube/Reddit commentary is frequently Hinglish, which
    # previously contributed zero sentiment signal). Deliberately a small,
    # common, low-ambiguity set — not exhaustive — to avoid false-positive
    # collisions with unrelated English usage.
    "achha", "accha", "badhiya", "zabardast", "kamaal", "shandar",
    "behtareen", "khoobsurat", "sundar", "mast",
})
_NEGATIVE_WORDS = frozenset({
    "avoid", "closed", "crowded", "dirty", "disappointing", "expensive", "meh",
    "overhyped", "overpriced", "overrated", "packed", "queue", "queues", "scam",
    "skip", "touristy", "trap", "waste",
    # Romanized Hindi/Hinglish supplement — see positive-side comment above.
    "bekar", "bekaar", "ganda", "faaltu", "bakwas", "mehenga", "mehanga", "dhoka",
})

# POI names that are a single generic word produce false mention matches
# ("park", "market", …) — exclude them from matching entirely.
_GENERIC_NAMES = frozenset({
    "park", "museum", "temple", "beach", "market", "cafe", "restaurant",
    "hotel", "church", "garden", "lake", "fort", "mall", "zoo", "bar",
    "castle", "tower", "bridge", "station", "harbour", "harbor",
})

# destination -> (computed_at_epoch, intel dict)
_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()


def _scroll_destination(client, collection: str, destination: str, limit: int) -> list[dict]:
    dest_filter = Filter(
        must=[FieldCondition(key="destination", match=MatchValue(value=destination))]
    )
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=dest_filter,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [p.payload or {} for p in points]


def _sentiment_around(chunk_lower: str, name_lower: str) -> tuple[int, int]:
    """Count positive/negative lexicon words within ±_SENTIMENT_WINDOW chars
    of every occurrence of `name_lower` in `chunk_lower`."""
    pos = neg = 0
    start = 0
    while True:
        idx = chunk_lower.find(name_lower, start)
        if idx == -1:
            break
        window = chunk_lower[max(0, idx - _SENTIMENT_WINDOW): idx + len(name_lower) + _SENTIMENT_WINDOW]
        words = set(window.replace(",", " ").replace(".", " ").replace("!", " ").split())
        pos += len(words & _POSITIVE_WORDS)
        neg += len(words & _NEGATIVE_WORDS)
        start = idx + len(name_lower)
    return pos, neg


def compute_gem_intel_sync(destination: str) -> dict:
    """One bounded pass over osm_pois × community-sentiment chunks for
    `destination`. Blends every configured sentiment source (currently
    Reddit + YouTube comments — docs/NEXT_SESSION_TODO.md item 3, added so
    the feature still has real signal to work with while Reddit ingestion
    stays blocked on API approval) with per-source provenance, instead of a
    single hardcoded collection.

    Returns {"gems": [...], "crowd_favourites": [...]}, each entry:
    {name, poi_type, lat, lon, mentions, sentiment, sources, gem_score}.
    `sources` is a list of "r/<subreddit>" / "YouTube" strings.
    Pure CPU + N Qdrant scrolls — call via asyncio.to_thread.
    """
    client = get_qdrant()
    pois = _scroll_destination(client, settings.qdrant_collection_osm, destination, _MAX_POIS)

    # Each sentiment source contributes chunks with a (text, provenance_label)
    # shape — provenance is source-specific (subreddit name vs. a flat
    # "YouTube" label, since individual video titles are too noisy to surface
    # as provenance the way a subreddit name is).
    chunks: list[tuple[str, str]] = []
    reddit_chunks = _scroll_destination(client, settings.qdrant_collection_reddit, destination, _MAX_CHUNKS)
    chunks.extend((c.get("text") or "", f"r/{c['subreddit']}" if c.get("subreddit") else "") for c in reddit_chunks)
    yt_chunks = _scroll_destination(
        client, settings.qdrant_collection_youtube_comments, destination, _MAX_CHUNKS
    )
    chunks.extend((c.get("text") or "", "YouTube") for c in yt_chunks)

    if not pois or not chunks:
        return {"gems": [], "crowd_favourites": []}

    # Pre-lowercase chunk texts once — the inner loop is pure substring search.
    chunk_lowers = [(t.lower(), label) for t, label in chunks]

    gems: list[dict] = []
    crowd: list[dict] = []
    for poi in pois:
        name = (poi.get("name") or "").strip()
        name_lower = name.lower()
        if len(name_lower) < 4 or name_lower in _GENERIC_NAMES:
            continue

        mentions = 0
        pos_total = neg_total = 0
        sources: list[str] = []
        for chunk_lower, label in chunk_lowers:
            if name_lower not in chunk_lower:
                continue
            mentions += 1
            pos, neg = _sentiment_around(chunk_lower, name_lower)
            pos_total += pos
            neg_total += neg
            if label and label not in sources:
                sources.append(label)

        if mentions == 0:
            continue  # no community proof — never recommend on OSM presence alone

        # Laplace smoothing so a single unopposed positive word doesn't read
        # as 100% and zero-signal mentions read as neutral 0.5.
        sentiment = (pos_total + 1) / (pos_total + neg_total + 2)
        entry = {
            "name": name,
            "poi_type": poi.get("poi_type", ""),
            "lat": poi.get("lat", 0.0),
            "lon": poi.get("lon", 0.0),
            "mentions": mentions,
            "sentiment": round(sentiment, 3),
            "sources": sources[:2],
            # Fewer mentions rank higher at equal sentiment — that's the gem.
            "gem_score": round(sentiment / math.log2(2 + mentions), 4),
        }
        if mentions >= _CROWD_MIN_MENTIONS:
            crowd.append(entry)
        elif mentions <= _GEM_MAX_MENTIONS and sentiment >= _GEM_MIN_SENTIMENT:
            gems.append(entry)

    gems.sort(key=lambda g: g["gem_score"], reverse=True)
    crowd.sort(key=lambda g: g["mentions"], reverse=True)
    return {
        "gems": gems[:_MAX_GEMS],
        "crowd_favourites": crowd[:_MAX_CROWD_FAVOURITES],
    }


async def get_gem_intel(destination: str) -> dict:
    """Cached, stampede-safe async wrapper around compute_gem_intel_sync."""
    now = time.monotonic()
    cached = _cache.get(destination)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    async with _locks_guard:
        lock = _locks.setdefault(destination, asyncio.Lock())
    async with lock:
        cached = _cache.get(destination)  # re-check: another waiter computed it
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]
        intel = await asyncio.to_thread(compute_gem_intel_sync, destination)
        _cache[destination] = (time.monotonic(), intel)
        return intel


def gem_prompt_block(intel: dict, crowd_preference: str) -> str:
    """Format gem intel for prompt injection based on the user's crowd dial.

    Token budget: ≤ ~250 tokens (hard-capped list sizes) and injected only
    when the dial + data warrant it — "touristy" and empty-intel cases cost
    zero extra tokens.
    """
    gems = intel.get("gems", [])
    crowd = intel.get("crowd_favourites", [])

    if crowd_preference == "touristy" or not gems:
        return ""

    n_gems = 8 if crowd_preference == "offbeat" else 5
    lines = []
    for g in gems[:n_gems]:
        provenance = f"mentioned in {g['mentions']} traveller post(s)"
        if g["sources"]:
            provenance += " on " + ", ".join(g["sources"])
        lines.append(
            f"- {g['name']} ({g['poi_type']}, lat {g['lat']}, lon {g['lon']}) — {provenance}, "
            f"{round(g['sentiment'] * 100)}% positive sentiment"
        )

    block = (
        "HIDDEN GEM CANDIDATES (real places verified via OpenStreetMap; community "
        "signal mined from traveller posts — high praise, low crowd volume):\n"
        + "\n".join(lines)
    )
    if crowd_preference == "offbeat" and crowd:
        crowd_names = ", ".join(c["name"] for c in crowd[:_MAX_CROWD_FAVOURITES])
        block += (
            f"\nCROWD-HEAVY SPOTS (frequently mentioned — de-prioritise these, "
            f"keeping at most 1-2 as iconic anchors): {crowd_names}"
        )
    return block
