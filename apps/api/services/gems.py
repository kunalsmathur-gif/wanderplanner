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
import re
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
#
# Sized against the corpus, not by taste (re-audit 2026-07-27, 1,274 real
# mention windows from 54 destinations). The original lexicon fired on only
# **29%** of windows, and because Laplace smoothing puts a no-lexicon-word
# mention at exactly (0+1)/(0+0+2) = 0.5 — just under _GEM_MIN_SENTIMENT —
# "no opinion words nearby" was indistinguishable from "badly reviewed".
# That single fact accounted for **64 of the 94 destinations returning zero
# gems**: Red Fort, India Gate, Jama Masjid, Elephanta Caves and Marine Drive
# were all rejected with pos=0, neg=0. Only 25% of rejections were genuinely
# negative.
#
# ⚠️ THE ADDITIONS BELOW ARE NOT "OBVIOUS PRAISE WORDS" — READ THIS BEFORE
# ADDING MORE. The corpus is YouTube comments, where most enthusiasm is aimed
# at the *video*, not the place, and that text sits inside the same
# ±_SENTIMENT_WINDOW as the POI name. Measuring each candidate's enrichment
# for creator context (words like "video"/"vlog"/"channel"/"subscribe"
# co-occurring; 21.8% corpus baseline) splits them cleanly, and it is the
# opposite of intuition:
#
#   REJECTED — video-directed          ACCEPTED — place-directed
#   ------------------------------     ------------------------------
#   superb      4.6x   ("superb video") clean      0.0x
#   informative 3.4x                    delicious  0.0x
#   awesome     3.0x   ("you're awesome") historic 0.0x
#   helpful     2.8x   ("helpful video") must      0.3x  ("must visit")
#   wonderful   2.5x                    good       0.5x
#   fantastic   2.3x   ("fantastic duo") friendly  0.5x
#   nice        1.7x   ("nice vlog")     love      1.0x  ("i love jaipur")
#   great       1.7x   ("great video")   safe      1.2x
#
# "great" (97 windows) and "nice" (50) were the two largest available recall
# wins and are both mostly praise of the vlogger — adding them would have
# measured production quality and reported it as place quality. Net effect of
# taking only the place-directed half: lexicon coverage 29% → 43% while the
# share of firing windows that carry creator context stays flat (25% → 23%),
# i.e. recall roughly doubled without importing the confound.
_POSITIVE_WORDS = frozenset({
    "amazing", "authentic", "beautiful", "best", "calm", "charming", "favourite",
    "favorite", "gem", "gorgeous", "highlight", "incredible", "local", "lovely",
    "loved", "magical", "peaceful", "perfect", "quiet", "recommend", "serene",
    "stunning", "underrated", "unique", "worth",
    # Corpus-calibrated additions (2026-07-27) — every one measured at or below
    # the creator-context baseline, so they describe the place rather than the
    # video. Counts are windows out of 1,274.
    "love",         # 113, 0.97x — "i love jaipur pink city"
    "good",         #  53, 0.52x
    "friendly",     #  17, 0.54x — "the people are very friendly"
    "safe",         #  16, 1.15x — "i felt so safe walking the streets"
    "must",         #  14, 0.33x — "must visit", the strongest travel-text endorsement
    "clean",        #  11, 0.00x
    "delicious",    #   9, 0.00x
    "enjoyed",      #   9, 1.02x
    "fun",          #   8, 1.15x
    "historic",     #   6, 0.00x
    "interesting",  #   5, 0.92x
    "excellent",    #   3, 0.00x
    "spectacular",  #   3, 0.00x
    "divine",       #   3, 0.00x
    "affordable",   #   3, 0.00x
    "enjoying",     #   3, 0.00x
    "breathtaking", #   2, 0.00x
    "relaxing",     #   2, 0.00x
    "impressive",   #   1, 0.00x
    # Deliberately NOT added despite corpus presence: "famous"/"iconic" are
    # descriptive rather than evaluative (and a place called famous is by
    # definition not a hidden gem); "cool" and "green" are ambiguous with
    # climate and foliage, which matters for the hill stations in the
    # catalogue ("cool weather in Munnar"); "enjoy" skews to future intent
    # about the trip or the video, where "enjoyed"/"enjoying" report an
    # actual visit; "cheap" reads as a complaint about as often as praise.
    #
    # Romanized Hindi/Hinglish supplement (docs/NEXT_SESSION_TODO.md item 3:
    # domestic-travel YouTube/Reddit commentary is frequently Hinglish, which
    # previously contributed zero sentiment signal). Deliberately a small,
    # common, low-ambiguity set — not exhaustive — to avoid false-positive
    # collisions with unrelated English usage.
    "achha", "accha", "badhiya", "zabardast", "kamaal", "shandar",
    "behtareen", "khoobsurat", "sundar", "mast",
})
# The negative side is genuinely sparse and that is a property of the corpus,
# not an oversight: people rarely post criticism under a travel vlog. The most
# frequent negatives in the 1,274 windows ("crowded" 7, "skip" 6, "expensive"
# 5, "overrated" 5, "waste" 5, "packed" 5, "closed" 5) were already covered;
# the additions below are everything else that occurred at all. "traffic" and
# "hot" were rejected as descriptive rather than evaluative — "hot" in
# particular is weather for most of the Indian catalogue.
_NEGATIVE_WORDS = frozenset({
    "avoid", "closed", "crowded", "dirty", "disappointing", "expensive", "meh",
    "overhyped", "overpriced", "overrated", "packed", "queue", "queues", "scam",
    "skip", "touristy", "trap", "waste",
    # Corpus-calibrated additions (2026-07-27).
    "bad", "poor", "worst", "rude", "boring", "difficult",
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


def _resolve_overlapping_mentions(
    hits: list[tuple[int, int, int, bool]],
) -> list[tuple[int, int, int, bool]]:
    """Drop any (poi_index, start, end, matched_exact_name) hit that a
    *different* POI claimed more specifically at the same place in the text.

    `build_mention_pattern` already resolves longest-first within one POI's own
    variants, but nothing did so *between* POIs, and OSM pools routinely hold
    one name nested inside another. Live-observed on the 2026-07-27 re-audit,
    in both directions:

    - "visited the grand egyptian museum" credited a mention to Cairo's
      **Egyptian Museum** as well as to the **Grand Egyptian Museum**. These
      are two genuinely different museums, so neither POI can be dropped from
      the pool — the individual mention simply belongs to one of them.
    - The reverse: "Lotte World is lovely" credited **Lotte World Tower**,
      because `name_variants` peels the structural word "tower" and leaves a
      variant identical to the other POI's real name.

    Two rules, applied together:

    1. **Longer containment wins.** A span strictly inside a longer span from
       another POI is that other POI's mention. Equal-length spans cannot be
       two different names, and a partial overlap is not a nesting.
    2. **An exact name beats a derived variant at the same span.** When both
       POIs match the identical text, the one whose *full* name is that text
       owns it; the other only got there by peeling a structural word off, and
       a guess must not outrank an identity.
    """
    if len(hits) < 2:
        return hits
    kept = []
    for idx, start, end, exact in hits:
        swallowed = any(
            other_idx != idx
            and other_start <= start
            and end <= other_end
            and (
                (other_end - other_start) > (end - start)
                # Rule 2 — same span, and the other POI matched it by its real
                # name while this one only matched a peeled variant.
                or ((other_start, other_end) == (start, end) and other_exact and not exact)
            )
            for other_idx, other_start, other_end, other_exact in hits
        )
        if not swallowed:
            kept.append((idx, start, end, exact))
    return kept


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

    # Pass 0 — the candidate set. Filtering happens here so the scoring pass
    # below can be organised by chunk rather than by POI, which is what makes
    # cross-POI mention attribution possible.
    destination_norm = normalize_name(destination)
    candidates: list[tuple[dict, str, list[str], re.Pattern[str]]] = []
    seen_norms: dict[str, int] = {}
    for poi in pois:
        name = (poi.get("name") or "").strip()
        if poi.get("poi_type") in _NON_GEM_POI_TYPES:
            continue
        # A POI named after the destination itself is the destination, not a
        # find within it — live-observed: Khajuraho's strongest "gem" was a
        # POI called "Khajuraho", matching every comment that named the town.
        name_norm = normalize_name(name)
        if name_norm == destination_norm:
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

        # Two OSM nodes can carry the same name and both get ingested — Jaipur
        # holds a "Pink city" (museum) and a "Pink City" (attraction), which
        # normalise identically and surfaced as two separate "finds" in the
        # same gem list. They match the same text, so they would also always
        # score identically; keep the better-tagged one and drop the rest.
        # Only *exact* normalised equality is collapsed here — near-duplicates
        # are handled by attribution instead (see _resolve_overlapping_mentions),
        # because containment does not imply sameness.
        if name_norm in seen_norms:
            kept = candidates[seen_norms[name_norm]][0]
            if (poi.get("prominence") or 0) > (kept.get("prominence") or 0):
                candidates[seen_norms[name_norm]] = (poi, name, variants, pattern)
            continue
        seen_norms[name_norm] = len(candidates)
        candidates.append((poi, name, variants, pattern))

    # Pass 1 — score every POI with at least one community mention. The
    # gem/crowd split can't happen inline any more: the crowd threshold is
    # derived from the destination's own mention distribution, which isn't
    # known until every POI has been counted.
    #
    # Organised chunk-outer / POI-inner so every POI matching a given chunk is
    # known at once and a nested name can be attributed to the POI that
    # actually earned it. Same total work as the old POI-outer loop — the
    # cheap substring prefilter still gates the regex.
    stats: list[dict] = [
        {"mentions": 0, "pos": 0, "neg": 0, "sources": []} for _ in candidates
    ]
    for chunk_norm, label in chunk_norms:
        hits: list[tuple[int, int, int, bool]] = []
        for idx, (_poi, name, variants, pattern) in enumerate(candidates):
            if not any(v in chunk_norm for v in variants):
                continue
            full_name_norm = normalize_name(name)
            for match in pattern.finditer(chunk_norm):
                start, end = match.span()
                hits.append((idx, start, end, match.group() == full_name_norm))
        if not hits:
            continue

        spans_by_candidate: dict[int, list[tuple[int, int]]] = {}
        for idx, start, end, _exact in _resolve_overlapping_mentions(hits):
            spans_by_candidate.setdefault(idx, []).append((start, end))

        for idx, spans in spans_by_candidate.items():
            entry = stats[idx]
            entry["mentions"] += 1
            pos, neg = _sentiment_around(chunk_norm, spans)
            entry["pos"] += pos
            entry["neg"] += neg
            if label and label not in entry["sources"]:
                entry["sources"].append(label)

    scored: list[dict] = []
    for (poi, name, _variants, _pattern), entry in zip(candidates, stats):
        if entry["mentions"] == 0:
            continue  # no community proof — never recommend on OSM presence alone

        # Laplace smoothing so a single unopposed positive word doesn't read
        # as 100% and zero-signal mentions read as neutral 0.5.
        sentiment = (entry["pos"] + 1) / (entry["pos"] + entry["neg"] + 2)
        scored.append({
            "name": name,
            "poi_type": poi.get("poi_type", ""),
            "lat": poi.get("lat", 0.0),
            "lon": poi.get("lon", 0.0),
            "mentions": entry["mentions"],
            "sentiment": round(sentiment, 3),
            "sources": entry["sources"][:2],
            # Fewer mentions rank higher at equal sentiment — that's the gem.
            "gem_score": round(sentiment / math.log2(2 + entry["mentions"]), 4),
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
