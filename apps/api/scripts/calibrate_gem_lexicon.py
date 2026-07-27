"""Calibrate services/gems.py's sentiment lexicon against the real corpus.

**Run this before adding any word to `_POSITIVE_WORDS` / `_NEGATIVE_WORDS`.**

The lexicon is load-bearing in a way that is easy to miss: Laplace smoothing
scores a mention with no lexicon word in range at exactly (0+1)/(0+0+2) = 0.5,
just under `_GEM_MIN_SENTIMENT` (0.55). So the "sentiment floor" is really an
"at least one lexicon hit" gate, and a word that is missing does not merely
weaken a score — it deletes the POI from both output lists.

The trap this script exists to prevent
--------------------------------------
The corpus is YouTube comments, where most enthusiasm is aimed at the **video**
rather than the place, and that praise sits inside the same +/-`_SENTIMENT_WINDOW`
as the POI name. Picking "obvious praise words" by hand therefore measures
production quality and reports it as place quality.

Measured 2026-07-27 over 1,274 real mention windows from 54 destinations
(baseline: 21.8% of all windows contain a creator marker):

    REJECTED - video-directed          ACCEPTED - place-directed
    superb       4.6x                  clean        0.0x
    informative  3.4x                  delicious    0.0x
    awesome      3.0x                  historic     0.0x
    helpful      2.8x                  must         0.3x
    wonderful    2.5x                  good         0.5x
    fantastic    2.3x                  friendly     0.5x
    nice         1.7x                  love         1.0x
    great        1.7x                  safe         1.2x

`great` (97 windows) and `nice` (50) were the two largest available recall
wins and are mostly praise of the vlogger. Taking only the place-directed half
moved lexicon coverage 29% -> 43% while the creator-context share of firing
windows stayed flat (25% -> 23%).

    cd apps/api && venv/Scripts/python.exe scripts/calibrate_gem_lexicon.py

Read-only. The collected windows are cached to `scripts/out/` so candidates can
be re-scored without re-scrolling the cluster (the collection pass takes ~10
minutes); `scripts/baselines/` holds the committed 2026-07-27 sample, which is
used automatically when no local cache exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings  # noqa: E402
from core.logging_config import configure_script_logging  # noqa: E402
from core.qdrant import get_qdrant  # noqa: E402
from services import gems as G  # noqa: E402
from services.name_matching import (  # noqa: E402
    build_mention_pattern,
    name_variants,
    normalize_name,
)

CACHE_PATH = Path(__file__).parent / "out" / "gem_mention_windows.json"
BASELINE_PATH = Path(__file__).parent / "baselines" / "gem_mention_windows_20260727.json"

# Spread across India / Europe / SE-Asia / Americas / East Asia so the ranking
# is not dominated by one writing style or one language mix.
SAMPLE_DESTINATIONS = [
    "Delhi", "Mumbai", "Jaipur", "Agra", "Varanasi", "Bengaluru", "Chennai",
    "Kochi", "Goa", "Udaipur", "Rishikesh", "Darjeeling", "Munnar", "Coorg",
    "Amritsar", "Hyderabad", "Pondicherry", "Shimla", "Manali", "Kolkata",
    "Tokyo", "Kyoto", "Osaka", "Seoul", "Taipei", "Hong Kong", "Bangkok",
    "Chiang Mai", "Hanoi", "Bali", "Singapore", "Kuala Lumpur",
    "Paris", "London", "Rome", "Barcelona", "Berlin", "Amsterdam", "Prague",
    "Lisbon", "Vienna", "Budapest", "Istanbul", "Dublin", "Porto",
    "New York", "Los Angeles", "Toronto", "Vancouver", "Montreal",
    "Dubai", "Sydney", "Melbourne", "Cairo",
]

# Unambiguous markers that a sentence is about the video/creator, not a place.
CREATOR_MARKERS = frozenset({
    "video", "videos", "vlog", "vlogs", "channel", "subscribe", "subscribed",
    "watching", "watched", "content", "upload", "uploaded", "editing",
    "footage", "camera", "episode", "series", "bhaiya", "bro", "sir",
    "thumbnail", "commentary", "narration", "presenter",
})

# Edit this list to vet new candidates. Anything already in the lexicon is
# skipped automatically.
CANDIDATES = [
    "love", "great", "good", "nice", "wonderful", "awesome", "excellent",
    "fantastic", "superb", "enjoyed", "enjoy", "pretty", "clean", "friendly",
    "safe", "historic", "vibrant", "delicious", "must", "wow", "divine",
    "spectacular", "breathtaking", "fun", "helpful", "informative", "cheap",
    "affordable", "iconic", "famous", "interesting", "relaxing", "scenic",
    "impressive", "enjoying", "cool", "green",
]

# Enrichment at or above this is video-directed; below the lower bound is
# place-directed. Between them, judge on the word's own semantics.
REJECT_AT = 1.6
ACCEPT_BELOW = 1.15
# Below this many occurrences an enrichment ratio is noise, not a measurement.
MIN_OCCURRENCES_FOR_VERDICT = 8


def collect_windows() -> list[str]:
    """The actual +/-_SENTIMENT_WINDOW text around every POI mention."""
    client = get_qdrant()
    windows: list[str] = []
    for i, dest in enumerate(SAMPLE_DESTINATIONS, 1):
        try:
            pois = G._scroll_destination(
                client, settings.qdrant_collection_osm, dest, G._MAX_POIS)
            chunks = [c.get("text") or "" for c in G._scroll_destination(
                client, settings.qdrant_collection_youtube_comments, dest, G._MAX_CHUNKS)]
        except Exception as e:
            print(f"  {dest}: skipped ({type(e).__name__})", flush=True)
            continue
        chunk_norms = [normalize_name(t) for t in chunks]
        dest_norm = normalize_name(dest)
        found = 0
        for poi in pois:
            name = (poi.get("name") or "").strip()
            if poi.get("poi_type") in G._NON_GEM_POI_TYPES or normalize_name(name) == dest_norm:
                continue
            variants = name_variants(name)
            variants += [v for v in name_variants(poi.get("name_local") or "")
                         if v not in variants]
            pattern = build_mention_pattern(variants)
            if pattern is None:
                continue
            for chunk_norm in chunk_norms:
                if not any(v in chunk_norm for v in variants):
                    continue
                for match in pattern.finditer(chunk_norm):
                    start, end = match.span()
                    windows.append(chunk_norm[max(0, start - G._SENTIMENT_WINDOW):
                                              end + G._SENTIMENT_WINDOW])
                    found += 1
        print(f"[{i}/{len(SAMPLE_DESTINATIONS)}] {dest}: {found} mention windows", flush=True)
    return windows


def main() -> int:
    configure_script_logging()

    if CACHE_PATH.exists():
        windows = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        print(f"reusing {len(windows)} cached windows from {CACHE_PATH.name}")
    elif BASELINE_PATH.exists():
        windows = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        print(f"using committed baseline: {len(windows)} windows from {BASELINE_PATH.name}")
        print("(delete nothing to re-collect; remove this file or add a local cache to refresh)")
    else:
        windows = collect_windows()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(windows, ensure_ascii=False), encoding="utf-8")
        print(f"collected {len(windows)} windows -> {CACHE_PATH}")

    if not windows:
        print("no windows collected")
        return 1

    token_sets = [set(w.split()) for w in windows]
    current = G._POSITIVE_WORDS | G._NEGATIVE_WORDS
    baseline = sum(1 for s in token_sets if s & CREATOR_MARKERS) / len(token_sets)
    hit_now = sum(1 for s in token_sets if s & current)

    print(f"\nmention windows: {len(windows)}")
    print(f"current lexicon fires on: {hit_now} ({hit_now / len(windows):.0%})")
    print(f"creator-marker baseline: {baseline:.1%} of all windows\n")

    print(f"{'word':<15}{'n':>5}{'creator%':>10}{'enrich':>8}   verdict")
    print("-" * 64)
    rows = []
    for word in CANDIDATES:
        if word in current:
            continue
        hits = [s for s in token_sets if word in s]
        if not hits:
            continue
        frac = sum(1 for s in hits if s & CREATOR_MARKERS) / len(hits)
        enrich = frac / baseline if baseline else 0.0
        rows.append((word, len(hits), frac, enrich))

    for word, n, frac, enrich in sorted(rows, key=lambda r: -r[3]):
        if n < MIN_OCCURRENCES_FOR_VERDICT:
            verdict = f"too rare to judge (n<{MIN_OCCURRENCES_FOR_VERDICT}) — use semantics"
        elif enrich >= REJECT_AT:
            verdict = "REJECT — video-directed"
        elif enrich >= ACCEPT_BELOW:
            verdict = "borderline"
        else:
            verdict = "accept — place-directed"
        print(f"{word:<15}{n:>5}{frac:>9.0%}{enrich:>8.2f}   {verdict}")

    accepted = {w for w, n, _f, e in rows if n >= MIN_OCCURRENCES_FOR_VERDICT and e < ACCEPT_BELOW}
    if accepted:
        lex = current | accepted
        hit = sum(1 for s in token_sets if s & lex)
        conf = sum(1 for s in token_sets if (s & lex) and (s & CREATOR_MARKERS))
        print(f"\nwith the accepted additions: fires on {hit} ({hit / len(windows):.0%}), "
              f"of which creator-context {conf / hit:.0%}")
        print("⚠️  If that creator-context share RISES materially, the additions are "
              "importing the confound — reject them however good the recall looks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
