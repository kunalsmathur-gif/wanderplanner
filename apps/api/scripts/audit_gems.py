"""Full-corpus read-only audit of what services/gems.py actually returns.

Every gem audit before 2026-07-27 sampled 8 destinations, which was enough to
find bugs but never enough to say whether the *feature* works. This runs all
of `KNOWN_DESTINATIONS` against the live cluster and reports both the output
and an attribution of why each destination returns nothing.

    cd apps/api && venv/Scripts/python.exe scripts/audit_gems.py

Read-only — scrolls only, never writes. Resumable via a JSONL state file, and
takes no flags. Delete the state file to force a fresh run.

Why there is a replica of the scoring loop in here
--------------------------------------------------
`compute_gem_intel_sync` returns gems and crowd favourites, not *why* a
destination produced neither — and the interesting question is almost always
the why. So this walks the same matching pipeline to expose the intermediate
counts, then **cross-checks its own partition against what the real function
returned, for every destination** (`replica_matches_real`).

That check is the point, not a formality: during the v10.42.0 work the shipped
loop changed and this replica did not, and the flag caught the drift on 9
destinations rather than letting stale diagnostics be reported as fact. If
`replica_matches_real` is False anywhere, the diagnostic columns for that row
are not to be trusted and this file needs re-syncing with services/gems.py.
The headline `n_gems`/`n_crowd` always come from the real function.

Baselines
---------
`scripts/baselines/` holds the pre-v10.42.0 run. That one cannot be
regenerated — the scoring code has changed since — so it is committed rather
than left to a scratch directory.
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings  # noqa: E402
from core.logging_config import configure_script_logging  # noqa: E402
from core.qdrant import get_qdrant  # noqa: E402
from scrapers.reddit import KNOWN_DESTINATIONS  # noqa: E402
from services import gems as G  # noqa: E402
from services.name_matching import (  # noqa: E402
    build_mention_pattern,
    name_variants,
    normalize_name,
)

STATE_PATH = Path(__file__).parent / "out" / "audit_gems.jsonl"


def _retry(fn: Any, attempts: int = 3, delay: float = 4.0) -> Any:
    """Qdrant Cloud read timeouts on this cluster are transient (v10.40.2, where
    8 of 90 failures all passed on immediate retry) — so retry rather than
    recording a failure that isn't one."""
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))
    raise AssertionError("unreachable")


def audit_destination(destination: str) -> dict[str, Any]:
    client = get_qdrant()
    pois = _retry(lambda: G._scroll_destination(
        client, settings.qdrant_collection_osm, destination, G._MAX_POIS))
    reddit_chunks = _retry(lambda: G._scroll_destination(
        client, settings.qdrant_collection_reddit, destination, G._MAX_CHUNKS))
    yt_chunks = _retry(lambda: G._scroll_destination(
        client, settings.qdrant_collection_youtube_comments, destination, G._MAX_CHUNKS))

    chunks: list[tuple[str, str]] = [
        (c.get("text") or "", f"r/{c['subreddit']}" if c.get("subreddit") else "")
        for c in reddit_chunks
    ]
    chunks += [(c.get("text") or "", "YouTube") for c in yt_chunks]

    row: dict[str, Any] = {
        "destination": destination,
        "n_pois": len(pois),
        "n_chunks": len(chunks),
        "n_reddit": len(reddit_chunks),
        "n_youtube": len(yt_chunks),
    }

    # --- replica of compute_gem_intel_sync's candidate build ---
    destination_norm = normalize_name(destination)
    n_transport = n_self_named = n_no_pattern = n_duplicate = 0
    candidates: list[tuple[dict, str, list[str], re.Pattern[str]]] = []
    seen_norms: dict[str, int] = {}
    for poi in pois:
        name = (poi.get("name") or "").strip()
        if poi.get("poi_type") in G._NON_GEM_POI_TYPES:
            n_transport += 1
            continue
        name_norm = normalize_name(name)
        if name_norm == destination_norm:
            n_self_named += 1
            continue
        variants = name_variants(name)
        variants += [v for v in name_variants(poi.get("name_local") or "") if v not in variants]
        pattern = build_mention_pattern(variants)
        if pattern is None:
            n_no_pattern += 1
            continue
        if name_norm in seen_norms:
            n_duplicate += 1
            kept = candidates[seen_norms[name_norm]][0]
            if (poi.get("prominence") or 0) > (kept.get("prominence") or 0):
                candidates[seen_norms[name_norm]] = (poi, name, variants, pattern)
            continue
        seen_norms[name_norm] = len(candidates)
        candidates.append((poi, name, variants, pattern))

    # --- replica of the chunk-outer scoring pass with cross-POI attribution ---
    chunk_norms = [(normalize_name(t), label) for t, label in chunks]
    stats = [{"mentions": 0, "pos": 0, "neg": 0} for _ in candidates]
    for chunk_norm, _label in chunk_norms:
        hits: list[tuple[int, int, int, bool]] = []
        for idx, (_poi, name, variants, pattern) in enumerate(candidates):
            if not any(v in chunk_norm for v in variants):
                continue
            full_norm = normalize_name(name)
            for match in pattern.finditer(chunk_norm):
                start, end = match.span()
                hits.append((idx, start, end, match.group() == full_norm))
        if not hits:
            continue
        spans_by: dict[int, list[tuple[int, int]]] = {}
        for idx, start, end, _exact in G._resolve_overlapping_mentions(hits):
            spans_by.setdefault(idx, []).append((start, end))
        for idx, spans in spans_by.items():
            stats[idx]["mentions"] += 1
            pos, neg = G._sentiment_around(chunk_norm, spans)
            stats[idx]["pos"] += pos
            stats[idx]["neg"] += neg

    scored: list[dict[str, Any]] = []
    for (poi, name, _v, _p), entry in zip(candidates, stats):
        if entry["mentions"] == 0:
            continue
        sentiment = (entry["pos"] + 1) / (entry["pos"] + entry["neg"] + 2)
        scored.append({
            "name": name,
            "poi_type": poi.get("poi_type", ""),
            "mentions": entry["mentions"],
            "sentiment": round(sentiment, 3),
            "gem_score": round(sentiment / math.log2(2 + entry["mentions"]), 4),
        })

    row["n_transport_excluded"] = n_transport
    row["n_self_named_excluded"] = n_self_named
    row["n_no_pattern"] = n_no_pattern
    row["n_duplicate_collapsed"] = n_duplicate
    row["n_candidates"] = len(candidates)
    row["n_matched"] = len(scored)

    if scored:
        threshold = G._crowd_mention_threshold([e["mentions"] for e in scored])
        row["crowd_threshold"] = threshold
        row["max_mentions"] = max(e["mentions"] for e in scored)
        # Matched but in NEITHER list: under the crowd threshold and under the
        # sentiment floor. Post-v10.42.0 this is the only way a match vanishes.
        row["n_below_sentiment_floor"] = sum(
            1 for e in scored
            if e["mentions"] < threshold and e["sentiment"] < G._GEM_MIN_SENTIMENT
        )
        row["top_matches"] = sorted(scored, key=lambda e: e["mentions"], reverse=True)[:5]
    else:
        row["crowd_threshold"] = None
        row["max_mentions"] = 0
        row["n_below_sentiment_floor"] = 0
        row["top_matches"] = []

    # --- the shipped code path; headline numbers come from here ---
    real = _retry(lambda: G.compute_gem_intel_sync(destination))
    row["gems"] = [
        {"name": g["name"], "mentions": g["mentions"], "sentiment": g["sentiment"],
         "poi_type": g["poi_type"]}
        for g in real["gems"]
    ]
    row["crowd_favourites"] = [
        {"name": c["name"], "mentions": c["mentions"]} for c in real["crowd_favourites"]
    ]
    row["n_gems"] = len(real["gems"])
    row["n_crowd"] = len(real["crowd_favourites"])

    if scored:
        th = row["crowd_threshold"]
        rep_gems = sorted(
            [e for e in scored if e["mentions"] < th and e["sentiment"] >= G._GEM_MIN_SENTIMENT],
            key=lambda g: g["gem_score"], reverse=True)[:G._MAX_GEMS]
        rep_crowd = sorted(
            [e for e in scored if e["mentions"] >= th],
            key=lambda g: g["mentions"], reverse=True)[:G._MAX_CROWD_FAVOURITES]
    else:
        rep_gems, rep_crowd = [], []
    row["replica_matches_real"] = (
        [g["name"] for g in rep_gems] == [g["name"] for g in real["gems"]]
        and [c["name"] for c in rep_crowd] == [c["name"] for c in real["crowd_favourites"]]
    )
    return row


def summarise(rows: list[dict[str, Any]]) -> None:
    n = len(rows)
    if not n:
        print("no rows")
        return
    mismatch = [r["destination"] for r in rows if not r["replica_matches_real"]]
    print(f"\ndestinations audited: {n}")
    print(f"replica/real mismatches: {len(mismatch)} {mismatch[:10]}")
    if mismatch:
        print("  ⚠️  diagnostics for those rows are STALE — re-sync this script "
              "with services/gems.py before trusting them")

    with_gems = sum(1 for r in rows if r["n_gems"] > 0)
    with_crowd = sum(1 for r in rows if r["n_crowd"] > 0)
    with_either = sum(1 for r in rows if r["n_gems"] > 0 or r["n_crowd"] > 0)
    print(f"\nreturns >=1 gem:             {with_gems:3d} / {n}  ({with_gems / n:.0%})")
    print(f"returns >=1 crowd favourite: {with_crowd:3d} / {n}  ({with_crowd / n:.0%})")
    print(f"returns SOMETHING:           {with_either:3d} / {n}  ({with_either / n:.0%})")
    print(f"total gems: {sum(r['n_gems'] for r in rows)}")
    print(f"total matched POIs: {sum(r['n_matched'] for r in rows)}")
    print(f"matched POIs lost to the sentiment floor: "
          f"{sum(r['n_below_sentiment_floor'] for r in rows)}")
    print(f"duplicate POIs collapsed: {sum(r.get('n_duplicate_collapsed', 0) for r in rows)}")

    print("\n=== ZERO-GEM ATTRIBUTION (mutually exclusive, pipeline order) ===")
    buckets: dict[str, list[str]] = {}
    for r in rows:
        if r["n_gems"] > 0:
            continue
        if r["n_pois"] == 0:
            key = "A. no OSM POIs ingested"
        elif r["n_chunks"] == 0:
            key = "B. no community chunks"
        elif r["n_candidates"] == 0:
            key = "C. all POIs filtered pre-match"
        elif r["n_matched"] == 0:
            key = "D. no POI name appears in any chunk"
        elif r["n_matched"] == r["n_crowd"]:
            key = "E. every match ranked as a crowd favourite"
        elif r["n_below_sentiment_floor"] > 0:
            key = "F. matches exist but fall under the sentiment floor"
        else:
            key = "G. unattributed"
        buckets.setdefault(key, []).append(r["destination"])
    for key in sorted(buckets):
        print(f"  {key}: {len(buckets[key])}")
        print(f"      e.g. {', '.join(buckets[key][:8])}")


def main() -> int:
    configure_script_logging()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    if STATE_PATH.exists():
        rows = [json.loads(line) for line in
                STATE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = {r["destination"] for r in rows}
    todo = [d for d in KNOWN_DESTINATIONS if d not in done]
    print(f"{len(done)} already audited, {len(todo)} to go", flush=True)

    with STATE_PATH.open("a", encoding="utf-8") as fh:
        for i, dest in enumerate(todo, 1):
            try:
                row = audit_destination(dest)
            except Exception as e:
                # Left pending on purpose: a transient cluster timeout must not
                # be recorded as an audited destination (v10.40.1's lesson).
                print(f"[{i}/{len(todo)}] {dest}: FAILED {type(e).__name__} — stays pending",
                      flush=True)
                continue
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            flag = "" if row["replica_matches_real"] else "  !! REPLICA MISMATCH"
            print(f"[{i}/{len(todo)}] {dest}: gems={row['n_gems']} crowd={row['n_crowd']} "
                  f"matched={row['n_matched']}/{row['n_candidates']} "
                  f"chunks={row['n_chunks']}{flag}", flush=True)

    summarise(rows)
    remaining = len([d for d in KNOWN_DESTINATIONS if d not in {r["destination"] for r in rows}])
    print(f"\n{remaining} still pending — re-run to retry" if remaining
          else "\n0 still pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
