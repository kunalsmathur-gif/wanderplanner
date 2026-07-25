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

Linking the two sides is `services/name_matching.py`: OSM writes "Matangeshwar
Temple", "Marine Drive, Kochi" and "Beyoğlu" where a traveller types
"Matangeshwar", "Marine Drive" and "Beyoglu". Comparing raw lowercase
substrings (what this module did until v10.39.0) found none of those, which is
most of why the feature returned empty lists for destinations that had
hundreds of real comments.


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

from qdrant_client.models import FieldCondition, Filter, MatchValue

from core.config import settings
from core.qdrant import get_qdrant
from services.name_matching import build_mention_pattern, name_variants, normalize_name

logger = logging.getLogger(__name__)

# Bounded-compute caps. 300 POIs × 800 chunks × a handful of name variants
# each ≈ half a million substring checks — hundreds of ms of CPU at the very
# worst, once per destination per day. The word-boundary regex runs only on
# chunks that clear the substring prefilter, so it costs nothing on the
# overwhelming majority that contain no candidate name at all.
_MAX_POIS = 300
_MAX_CHUNKS = 800
_CACHE_TTL_SECONDS = 24 * 3600

# Classification thresholds.
#
# The gem/crowd split is computed *relative to this destination's own mention
# distribution* rather than from a fixed pair of absolute counts. Two absolute
# thresholds (previously 6 and 12) had a structural flaw beyond needing
# tuning: they left a dead zone. Any POI mentioned 7-11 times was classified
# as neither a gem nor a crowd favourite and silently vanished from both
# lists — live-observed for Jaipur, whose single strongest match (Hawa Mahal,
# 8 mentions) fell straight into the gap, so `compute_gem_intel_sync` returned
# empty despite having real signal.
#
# Absolute counts also can't be right for more than one corpus size at a time:
# 8 mentions means "barely known" in a destination with 500 ingested comments
# and "the single most talked-about place here" in one with 30. The percentile
# split below is scale-free, so it stays correct as ingestion coverage grows —
# which matters because coverage is still actively changing per destination.
#
# The two guard rails keep the relative split honest at the extremes:
_CROWD_PERCENTILE = 0.80          # top ~20% of mentioned POIs = crowd favourites
_CROWD_MIN_MENTIONS = 3           # 1-2 mentions is never "crowd favourite", however thin the corpus
_CROWD_ABSOLUTE_MENTIONS = 12     # this many mentions is a crowd favourite regardless of percentile
# Below this many mentioned POIs a percentile is meaningless (with 1-2 POIs the
# top 20% is just "the highest one", which would make a lone 5-mention POI a
# "crowd favourite" and return zero gems) — fall back to the absolute ceiling.
_MIN_POIS_FOR_RELATIVE_SPLIT = 5
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

# POI types that are orientation landmarks rather than places anyone visits
# for their own sake. They are ingested on purpose (scrapers/osm.py keeps
# transport nodes so the itinerary LLM can anchor routes), but recommending
# one as a hidden gem is nonsense, and live output was full of exactly that:
# Istanbul's entire gem list was Kadıköy, Karaköy and Beyoğlu — three metro
# stops — while Jaipur's second-strongest match was a POI literally named
# "Railway Station" and Paris's candidate pool is almost all metro stations
# (the known category-share skew in docs/NEXT_SESSION_TODO.md). Excluded from
# crowd favourites too: "de-prioritise the train station" is not advice.
_NON_GEM_POI_TYPES = frozenset({"train station", "airport"})

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


def _sentiment_around(chunk_norm: str, spans: list[tuple[int, int]]) -> tuple[int, int]:
    """Count positive/negative lexicon words within ±_SENTIMENT_WINDOW chars
    of each matched mention in `chunk_norm`.

    Both arguments come from the normalised pipeline: `chunk_norm` has already
    been folded and stripped of punctuation by name_matching.normalize_name,
    so a plain whitespace split yields clean lexicon tokens (the previous
    version hand-replaced a few punctuation marks and missed the rest).
    """
    pos = neg = 0
    for start, end in spans:
        window = chunk_norm[max(0, start - _SENTIMENT_WINDOW): end + _SENTIMENT_WINDOW]
        words = set(window.split())
        pos += len(words & _POSITIVE_WORDS)
        neg += len(words & _NEGATIVE_WORDS)
    return pos, neg


def _crowd_mention_threshold(mention_counts: list[int]) -> int:
    """Mention count at or above which a POI counts as a crowd favourite for
    *this* destination — see the threshold block above for why this is
    relative rather than absolute.

    Clamped into [_CROWD_MIN_MENTIONS, _CROWD_ABSOLUTE_MENTIONS] so a
    well-covered destination can't push the bar so high that genuinely
    famous places get called gems, and a thin one can't push it so low that
    a couple of passing mentions reads as a crowd.
    """
    if len(mention_counts) < _MIN_POIS_FOR_RELATIVE_SPLIT:
        return _CROWD_ABSOLUTE_MENTIONS
    ordered = sorted(mention_counts)
    idx = min(int(len(ordered) * _CROWD_PERCENTILE), len(ordered) - 1)
    return max(_CROWD_MIN_MENTIONS, min(ordered[idx], _CROWD_ABSOLUTE_MENTIONS))


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

    # Normalise chunk text once — folded and punctuation-stripped, so POI
    # names meet comment text in the same alphabet. Without this a diacritic
    # in the OSM name ("Beyoğlu", "Musée Grévin") made the POI unfindable in
    # comments typed on an English keyboard.
    chunk_norms = [(normalize_name(t), label) for t, label in chunks]

    # Pass 1 — score every POI with at least one community mention. The
    # gem/crowd split can't happen inline any more: the crowd threshold is
    # derived from the destination's own mention distribution, which isn't
    # known until every POI has been counted.
    destination_norm = normalize_name(destination)
    scored: list[dict] = []
    for poi in pois:
        name = (poi.get("name") or "").strip()
        if poi.get("poi_type") in _NON_GEM_POI_TYPES:
            continue
        # A POI named after the destination itself is the destination, not a
        # find within it — live-observed: Khajuraho's strongest "gem" was a
        # POI called "Khajuraho", matching every comment that named the town.
        if normalize_name(name) == destination_norm:
            continue

        # `name_local` is only present on POIs ingested after scrapers/osm.py
        # started preferring an English name. It earns its keep when `name:en`
        # is a *translation* rather than a transliteration — OSM's "Musée de
        # l'Armée"/"Army Museum" — where the local form is a genuinely
        # different string a comment might use. A non-Latin local name
        # normalises to nothing and simply contributes no variants, which is
        # the honest outcome: this matcher works in one alphabet.
        variants = name_variants(name)
        variants += [v for v in name_variants(poi.get("name_local") or "") if v not in variants]
        pattern = build_mention_pattern(variants)
        if pattern is None:
            continue

        mentions = 0
        pos_total = neg_total = 0
        sources: list[str] = []
        for chunk_norm, label in chunk_norms:
            # Cheap substring prefilter before the regex — keeps the inner
            # loop at the same cost as the old plain-substring scan, with the
            # boundary check paid only on the few chunks that can match.
            if not any(v in chunk_norm for v in variants):
                continue
            spans = [m.span() for m in pattern.finditer(chunk_norm)]
            if not spans:
                continue
            mentions += 1
            pos, neg = _sentiment_around(chunk_norm, spans)
            pos_total += pos
            neg_total += neg
            if label and label not in sources:
                sources.append(label)

        if mentions == 0:
            continue  # no community proof — never recommend on OSM presence alone

        # Laplace smoothing so a single unopposed positive word doesn't read
        # as 100% and zero-signal mentions read as neutral 0.5.
        sentiment = (pos_total + 1) / (pos_total + neg_total + 2)
        scored.append({
            "name": name,
            "poi_type": poi.get("poi_type", ""),
            "lat": poi.get("lat", 0.0),
            "lon": poi.get("lon", 0.0),
            "mentions": mentions,
            "sentiment": round(sentiment, 3),
            "sources": sources[:2],
            # Fewer mentions rank higher at equal sentiment — that's the gem.
            "gem_score": round(sentiment / math.log2(2 + mentions), 4),
        })

    if not scored:
        return {"gems": [], "crowd_favourites": []}

    # Pass 2 — classify against this destination's own distribution. The two
    # branches partition every mentioned POI, so nothing can fall between them
    # the way the old fixed 6/12 pair allowed; the sentiment floor is now the
    # only reason a mentioned POI appears in neither list, which is deliberate
    # (a poorly-reviewed obscure place is not a "hidden gem").
    crowd_threshold = _crowd_mention_threshold([e["mentions"] for e in scored])
    gems: list[dict] = []
    crowd: list[dict] = []
    for entry in scored:
        if entry["mentions"] >= crowd_threshold:
            crowd.append(entry)
        elif entry["sentiment"] >= _GEM_MIN_SENTIMENT:
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
