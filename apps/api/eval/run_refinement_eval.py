"""Refinement-fidelity eval runner — the GTM Phase 1 kill-criterion gate
(docs/GTM_STRATEGY.md §5: "if the fidelity evals can't measurably beat
ChatGPT, the consumer differentiation story is dead").

Per case in eval/refinement_fidelity_dataset.json, exercises the v10.17
refinement hard-constraints pipeline end-to-end:

    named interest → candidate expansion → OSM/wiki verification → pins in
    config_patch → itinerary generation (pins must appear exactly once with
    the "pinned" tag) → an unrelated second refinement + regeneration (pins
    must survive — diff fidelity).

Two modes:

  offline (default) — deterministic and free. The interest-expansion LLM
      call is replayed from the dataset's `offline_candidates`; generation
      uses the mock itinerary path. Verification, pin merging, prompt-block
      and inclusion/stability scoring all run the REAL production code.
      This is the regression gate.

  --live — real Gemini expansion, detection (chat_refine) and generation.
      Needs GEMINI_API_KEY + llm_provider != mock. This produces the
      kill-criterion numbers. Cost ≈ 2 itinerary generations + 1 expansion
      + 1 refine call per case (~$0.02/case on gemini-2.5-flash).

Both modes force an IN-MEMORY Qdrant seeded with the dataset's fixture
truth-set — the eval never touches (or pollutes) real ingested collections.

ChatGPT comparison: record ChatGPT's answers to the same prompts in
eval/baselines/chatgpt_refinement.json (copy the .template.json, paste each
case's `prompt_to_paste` into a fresh ChatGPT session, list every specific
place it suggests). Then run with --baseline to score both systems with the
same matcher and emit the comparison table.

Usage (from apps/api, venv python):
    python -m eval.run_refinement_eval
    python -m eval.run_refinement_eval --live
    python -m eval.run_refinement_eval --baseline eval/baselines/chatgpt_refinement.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

from core.config import settings

# Windows consoles default to cp1252, which can't print the ✅/❌ status
# marks — reconfigure rather than strip them (the report file is UTF-8 anyway).
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The eval must never write fixture data into a real Qdrant. Force :memory:
# BEFORE anything calls core.qdrant.get_qdrant() (module import is safe —
# the client is created lazily on first call).
settings.qdrant_url = ":memory:"

from qdrant_client.models import PointStruct  # noqa: E402

from chains.chat_refine_chain import (  # noqa: E402
    ChatRefineRequest,
    ChatRefineResponse,
    _apply_interest_pinning,
    chat_refine,
)
from chains.itinerary_chain import generate_itinerary  # noqa: E402
from core.qdrant import get_qdrant  # noqa: E402
from eval.refinement_scoring import (  # noqa: E402
    aggregate,
    aggregate_baseline,
    render_report,
    score_baseline_case,
    score_negative_case,
    score_positive_case,
)
from models.chat import ChatMessage  # noqa: E402
from models.trip import DestinationInput, PinnedPOI, TripConfig  # noqa: E402

DATASET_PATH = Path(__file__).parent / "refinement_fidelity_dataset.json"
OUT_DIR = Path(__file__).parent / "out"

_ZERO_VECTOR = [0.0] * 384  # verification only scrolls payloads — no vector search


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def seed_fixtures(fixtures: dict) -> None:
    """Seed the controlled truth-set into the in-memory Qdrant. Zero vectors
    on purpose: poi_pinning verification reads payloads via scroll, never by
    similarity, so the embedding model need not be loaded at all."""
    client = get_qdrant()
    osm_points = [
        PointStruct(id=i + 1, vector=_ZERO_VECTOR, payload=poi)
        for i, poi in enumerate(fixtures["osm_pois"])
    ]
    client.upsert(collection_name=settings.qdrant_collection_osm, points=osm_points)
    wiki_points = [
        PointStruct(id=i + 1, vector=_ZERO_VECTOR, payload=chunk)
        for i, chunk in enumerate(fixtures["wiki"])
    ]
    client.upsert(collection_name=settings.qdrant_collection_wiki, points=wiki_points)


def build_trip(case: dict) -> TripConfig:
    return TripConfig(
        purpose="leisure",
        dates={"start": "2026-11-10", "end": "2026-11-14", "flexible": False},
        destination=DestinationInput(
            city=case["destination"],
            country=case["destination_country"],
            lat=case["dest_lat"],
            lon=case["dest_lon"],
        ),
        budget={"amount": 150000, "currency": "INR"},
    )


def flatten_items(itinerary) -> list[dict]:
    return [
        {"title": item.title, "tags": item.tags}
        for day in itinerary.days
        for item in day.items
    ]


async def _no_photos(queries: list[str]) -> list[None]:
    return [None] * len(queries)


async def refine_case(case: dict, trip: TripConfig, live: bool) -> ChatRefineResponse:
    """Run the refinement turn. Live mode exercises real detection via
    chat_refine; offline replays the dataset's recorded expansion through the
    real _apply_interest_pinning + verification path."""
    if live:
        return await chat_refine(ChatRefineRequest(
            messages=[ChatMessage(role="user", content=case["user_message"])],
            trip_config=trip,
        ))

    synthetic = ChatRefineResponse(
        reply="(offline replay)",
        action_type="patch_config",
        config_patch=None,
        major_change=False,
        named_interest=case["named_interest"],
    )

    async def _replayed_expansion(interest: str, destination: str) -> list[str]:
        return list(case["offline_candidates"])

    with patch(
        "chains.interest_expansion_chain.expand_interest_to_candidates",
        _replayed_expansion,
    ):
        return await _apply_interest_pinning(synthetic, trip)


async def run_case(case: dict, live: bool) -> dict:
    trip = build_trip(case)
    resp = await refine_case(case, trip, live)
    pin_names = [p.name for p in resp.pinned_pois]

    # Apply the patch the way the frontend does: pins land on the config,
    # then the itinerary is regenerated in place.
    patch_pins = (resp.config_patch or {}).get("pinned_pois", [])
    pinned = [PinnedPOI(**p) for p in patch_pins]
    trip_pinned = trip.model_copy(update={"pinned_pois": pinned})

    with patch("chains.itinerary_chain.get_day_photos", _no_photos):
        itinerary = await generate_itinerary(trip_pinned)
        items = flatten_items(itinerary)

        # Unrelated second refinement (pace change) + regeneration — the
        # diff-fidelity check: committed pins must survive.
        trip_refined = trip_pinned.model_copy(update={"pace": "relaxed"})
        refined = await generate_itinerary(trip_refined)
        refined_items = flatten_items(refined)

    if case["negative"]:
        return score_negative_case(case, pin_names, items)

    candidates = list(case["offline_candidates"])
    if live:
        # In live mode the true candidate list is internal to chat_refine;
        # pins + dropped reconstruct it exactly (survivors + rejects).
        candidates = pin_names + list(resp.dropped_candidates)
    return score_positive_case(case, candidates, pin_names, items, refined_items)


def score_baseline(dataset: dict, baseline_path: Path) -> tuple[list[dict], dict]:
    recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in recorded.get("cases", [])}
    fixture_names_by_dest: dict[str, list[str]] = {}
    for poi in dataset["fixtures"]["osm_pois"]:
        fixture_names_by_dest.setdefault(poi["destination"], []).append(poi["name"])

    results = []
    missing = []
    for case in dataset["cases"]:
        entry = by_id.get(case["id"])
        if entry is None or "places" not in entry:
            missing.append(case["id"])
            continue
        results.append(score_baseline_case(
            case, entry["places"], fixture_names_by_dest.get(case["destination"], [])
        ))
    if missing:
        print(f"⚠️  baseline file has no recorded answer for: {', '.join(missing)}")
    return results, aggregate_baseline(results)


async def run(live: bool, baseline_path: Path | None) -> None:
    dataset = load_dataset()
    mode = "live" if live else "offline-replay"

    if live and settings.llm_provider == "mock":
        print("--live requires llm_provider != mock (set GEMINI_API_KEY / provider).")
        sys.exit(1)
    if not live:
        # Offline must be deterministic and free regardless of local .env.
        settings.llm_provider = "mock"

    print(f"Seeding {len(dataset['fixtures']['osm_pois'])} OSM + "
          f"{len(dataset['fixtures']['wiki'])} wiki fixtures into in-memory Qdrant…")
    seed_fixtures(dataset["fixtures"])

    print(f"Running {len(dataset['cases'])} refinement cases ({mode})…\n")
    results = []
    for case in dataset["cases"]:
        # One retry with backoff per case (live Gemini 503 blips), then record
        # the case as errored rather than killing a 20-case run — errored
        # cases are excluded from aggregates and flagged in the report.
        result = None
        for attempt in range(2):
            try:
                result = await run_case(case, live)
                break
            except Exception as exc:
                if attempt == 0:
                    print(f"…  {case['id']} errored ({exc}); retrying in 10s")
                    await asyncio.sleep(10)
                else:
                    print(f"❌ {case['id']} failed twice ({exc}); recorded as errored")
                    result = {
                        "id": case["id"], "destination": case["destination"],
                        "interest": case["named_interest"],
                        "negative": case["negative"], "error": str(exc),
                    }
        results.append(result)
        if "error" in result:
            continue
        if result["negative"]:
            status = "✅" if result["honest"] else "❌"
            print(f"{status} {result['id']}  {case['destination']:<12} "
                  f"[honesty] {case['named_interest']}")
        else:
            status = "✅" if result["fidelity"] >= 0.8 else ("⚠️" if result["fidelity"] > 0 else "❌")
            print(f"{status} {result['id']}  {case['destination']:<12} "
                  f"recall={result['pin_recall']:.2f} incl={result['inclusion_rate']:.2f} "
                  f"stab={result['stability_rate']:.2f} fid={result['fidelity']:.2f}  "
                  f"({case['named_interest']})")

    agg = aggregate(results)
    print("\n=== AGGREGATE ===")
    print(f"Refinement fidelity score: {agg['fidelity']:.3f}")
    print(f"Pin recall:                {agg['pin_recall']:.3f}")
    print(f"Inclusion (exactly-once):  {agg['inclusion_rate']:.3f}")
    print(f"Stability across refine:   {agg['stability_rate']:.3f}")
    print(f"Pin precision:             {agg['pin_precision']:.3f}")
    print(f"Honesty on impossible:     {agg['honesty_rate']:.0%}")

    baseline_results = baseline_agg = None
    if baseline_path is not None:
        baseline_results, baseline_agg = score_baseline(dataset, baseline_path)
        print("\n=== ChatGPT BASELINE ===")
        print(f"Verified-POI recall:       {baseline_agg['verified_recall']:.3f}")
        print(f"Unverifiable suggestions:  {baseline_agg['unverifiable_rate']:.3f}")
        print(f"Honesty on impossible:     {baseline_agg['honesty_rate']:.0%}")

    OUT_DIR.mkdir(exist_ok=True)
    report = render_report(results, agg, mode, baseline_results, baseline_agg)
    report_path = OUT_DIR / "refinement_fidelity_report.md"
    report_path.write_text(report, encoding="utf-8")
    json_path = OUT_DIR / "refinement_fidelity_results.json"
    json_path.write_text(
        json.dumps({"mode": mode, "aggregate": agg, "baseline": baseline_agg,
                    "results": results, "baseline_results": baseline_results}, indent=2),
        encoding="utf-8",
    )
    print(f"\nReport: {report_path}\nRaw:    {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="real Gemini detection/expansion/generation (costs money)")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="path to recorded ChatGPT answers JSON")
    args = parser.parse_args()
    asyncio.run(run(args.live, args.baseline))


if __name__ == "__main__":
    main()
