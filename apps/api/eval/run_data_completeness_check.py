"""Data-completeness pre-flight gate — run against the REAL Qdrant cluster
(not fixtures) for every destination in the golden/eval sets.

Recommended, not yet built as of docs/NEXT_SESSION_TODO.md's 2026-07-20
entry (item 13): the offline `refinement_fidelity` eval scores verification/
pinning *logic* against hand-curated fixtures seeded into an in-memory
Qdrant, so it structurally cannot detect a real production data-quality
regression (this is exactly how the 2026-07-20 session's OSM-category-
starvation and empty-wiki-collection bugs went unnoticed by the eval suite
despite it "scoring 1.000" — see docs/eval-set.md §4V and
eval/refinement_scoring.py's caveats).

This script closes that gap: for each destination already exercised by the
refinement-fidelity dataset, scroll the REAL `osm_pois`/`wiki` collections
and check:
    - non-zero wiki chunk count
    - a minimum OSM POI count
    - no single OSM tag category dominating the pool (the starvation bug)
(see eval/data_completeness_scoring.py for the exact thresholds/definitions.)

Run against the real cluster:
    cd apps/api && .venv/bin/python -m eval.run_data_completeness_check

Exits non-zero if any destination fails, so it can be wired into CI/a
scheduled job once there's an appetite for that (not done yet — manual run
recommended first per the "confirm per-destination with the user" guidance
already established for re-ingestion in NEXT_SESSION_TODO.md item 2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from core.config import settings
from core.qdrant import get_qdrant
from eval.data_completeness_scoring import aggregate, score_destination
from services.gems import _MAX_CHUNKS, _MAX_POIS, _scroll_destination

DATASET_PATH = Path(__file__).parent / "refinement_fidelity_dataset.json"


def golden_destinations() -> list[str]:
    """The destination set to pre-flight-check — reuses the refinement
    fidelity dataset's destination list (the same 16 real cities that
    dataset's cases already assume have usable OSM/wiki data) rather than
    maintaining a second, parallel list that could silently drift out of
    sync with it."""
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    seen: list[str] = []
    for case in data["cases"]:
        if case["destination"] not in seen:
            seen.append(case["destination"])
    return seen


def check_destination(client, destination: str) -> dict:
    wiki_chunks = _scroll_destination(client, settings.qdrant_collection_wiki, destination, _MAX_CHUNKS)
    osm_pois = _scroll_destination(client, settings.qdrant_collection_osm, destination, _MAX_POIS)
    return score_destination(destination, len(wiki_chunks), osm_pois)


def run() -> int:
    if settings.qdrant_url == ":memory:":
        print(
            "⚠️  QDRANT_URL is ':memory:' — this check is only meaningful against "
            "the REAL cluster (it exists to catch production ingestion bugs, not "
            "logic bugs the offline fixture eval already covers). Point QDRANT_URL/"
            "QDRANT_API_KEY at the real cluster before trusting this run.\n"
        )

    destinations = golden_destinations()
    client = get_qdrant()

    print(f"Checking data completeness for {len(destinations)} destinations...\n")
    results = [check_destination(client, d) for d in destinations]

    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(
            f"{status} {r['destination']:<12} wiki_chunks={r['wiki_chunk_count']:<4} "
            f"osm_pois={r['osm_poi_count']:<4} top_category="
            f"{r['top_category']}({r['top_category_share']:.0%})"
        )
        for failure in r["failures"]:
            print(f"     - {failure}")

    summary = aggregate(results)
    print(f"\n=== SUMMARY: {summary['passed']}/{summary['total']} passed "
          f"(pass_rate={summary['pass_rate']:.2f}) ===")
    if summary["failing_destinations"]:
        print(f"Failing destinations: {summary['failing_destinations']}")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
