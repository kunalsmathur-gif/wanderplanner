"""Scoring for the data-completeness pre-flight gate (found 2026-07-20, see
`docs/NEXT_SESSION_TODO.md` item 13 and `docs/eval-set.md` §4V).

Pure functions over plain data (a wiki chunk count + a list of OSM POI
payload dicts), so the runner and the unit tests share one set of
thresholds/definitions — same split as `eval/refinement_scoring.py`.

**Why this exists, and why it's separate from `fidelity`/`honest`:** the
2026-07-20 POI-pinning investigation found two real production data-quality
bugs — `scrapers/osm.py` producing 100%-food/drink POI pools for
already-ingested cities, and `scrapers/wikivoyage.py` silently returning zero
chunks for every destination — that the offline fixture-based fidelity eval
could not detect *by design* (it seeds its own self-contained fixtures into
an in-memory Qdrant, decoupled from whether real ingestion is healthy). This
module checks the *data*, not the *verification/pinning logic* — it answers
"is there enough real, well-distributed data for this destination to give
the pinning pipeline something honest to check candidates against", not
"does the pipeline behave correctly given good data" (that's `fidelity`).

Run this against a real Qdrant cluster (`eval/run_data_completeness_check.py`
— it will refuse to be meaningful against `:memory:`), not fixtures.
"""
from __future__ import annotations

from typing import Any

# Thresholds — deliberately conservative starting points, not derived from a
# rigorous study; tune once real POC traffic gives a sense of how much data
# actually moves itinerary quality. Documented here, not hidden in the
# runner, so a future recalibration is a one-line change with an obvious home.
MIN_WIKI_CHUNKS = 1        # the 2026-07-20 bug was *zero* everywhere — start here
MIN_OSM_POIS = 20          # rough floor for "enough variety to round-robin across categories"
MAX_CATEGORY_SHARE = 0.5   # no single OSM tag category may exceed this share of the pool


def score_destination(
    destination: str,
    wiki_chunk_count: int,
    osm_pois: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score one destination's real ingested data against the completeness
    thresholds. Returns a dict with per-check pass/fail plus the raw numbers
    a report renderer needs — never raises, always structurally the same
    shape so a runner can loop over destinations uniformly."""
    osm_poi_count = len(osm_pois)

    category_counts: dict[str, int] = {}
    for poi in osm_pois:
        category = (poi.get("poi_type") or "unknown").strip() or "unknown"
        category_counts[category] = category_counts.get(category, 0) + 1

    top_category = max(category_counts, key=category_counts.get) if category_counts else None
    top_category_share = (
        category_counts[top_category] / osm_poi_count if top_category and osm_poi_count else 0.0
    )

    failures: list[str] = []
    if wiki_chunk_count < MIN_WIKI_CHUNKS:
        failures.append(f"wiki_chunk_count={wiki_chunk_count} < MIN_WIKI_CHUNKS={MIN_WIKI_CHUNKS}")
    if osm_poi_count < MIN_OSM_POIS:
        failures.append(f"osm_poi_count={osm_poi_count} < MIN_OSM_POIS={MIN_OSM_POIS}")
    if top_category and top_category_share > MAX_CATEGORY_SHARE:
        failures.append(
            f"top_category='{top_category}' share={top_category_share:.2f} "
            f"> MAX_CATEGORY_SHARE={MAX_CATEGORY_SHARE}"
        )

    return {
        "destination": destination,
        "wiki_chunk_count": wiki_chunk_count,
        "osm_poi_count": osm_poi_count,
        "category_counts": category_counts,
        "top_category": top_category,
        "top_category_share": top_category_share,
        "passed": not failures,
        "failures": failures,
    }


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-destination results into a pass-rate summary — tracked as
    its own gate/metric, deliberately not folded into fidelity/honesty."""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "failing_destinations": [r["destination"] for r in results if not r["passed"]],
    }
