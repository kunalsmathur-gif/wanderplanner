"""LLM model-selection eval runner (docs/eval-set.md §8).

Answers the "should we run MMLU/GPQA to pick a model?" question the
2026-07-16 session raised — no, because those benchmarks say nothing about
itinerary-JSON fidelity, budget adherence, POI grounding, latency, or cost
at WanderPlanner's actual request shape. This runs each candidate model
against the REAL production prompt (chains.itinerary_chain.SYSTEM_PROMPT +
retrieved RAG context, identical across models) and scores:

    accuracy       — schema validity, day-count match, theme coverage,
                     budget adherence (see model_comparison_scoring.py)
    hallucination  — proxy rate of named places matching neither the
                     case's curated known-POI whitelist nor the retrieved
                     RAG context (documented caveat: upper-bound proxy,
                     not ground truth — fair for RELATIVE ranking only)
    latency        — wall-clock per call, p50/p95
    token cost     — per-request, from provider usage metadata +
                     core.llm_client's approximate pricing table
    scale cost     — token cost projected across --scale monthly volumes

COSTS REAL MONEY. Every model in --models makes one live API call per case
per --runs repeat. Default 6 cases x 3 runs x N models. Estimate before
running: with all 4 providers' cheapest tier that's ~72 calls, roughly a
few dollars — the runner prints an upfront estimate and requires --yes to
proceed non-interactively.

Missing API keys are NOT an error — that model is skipped with a note in
the report, so this runs today with whatever subset of keys are set in
.env and picks up more models later without code changes.

Usage (from apps/api, venv python):
    python -m eval.run_model_comparison --models gemini-2.5-flash,gemini-2.0-flash
    python -m eval.run_model_comparison --models gemini-2.5-flash,llama-3.1-70b-versatile,gpt-4o-mini,claude-3-5-haiku-20241022 --runs 3
    python -m eval.run_model_comparison --models <...> --scale 10000,100000,1000000 --yes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.config import settings

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Same isolation trick as run_refinement_eval.py — never touch real Qdrant.
settings.qdrant_url = ":memory:"

from qdrant_client.models import PointStruct  # noqa: E402

from chains.itinerary_chain import (  # noqa: E402
    SYSTEM_PROMPT,
    _budget_guidance_block,
    _gem_guidance_block,
    _itinerary_examples_block,
    _pinned_guidance_block,
)
from core.llm_client import estimate_cost_usd  # noqa: E402
from core.prompt_guard import neutralize, wrap_untrusted  # noqa: E402
from core.qdrant import get_qdrant  # noqa: E402
from eval.llm_providers import (  # noqa: E402
    MODEL_REGISTRY,
    call_model,
    is_available,
    strip_fences,
    unavailable_reason,
)
from eval.model_comparison_scoring import (  # noqa: E402
    accuracy_score,
    aggregate_model,
    hallucination_rate,
    render_report,
)
from eval.judge_metrics import JUDGE_MODEL, judge_available, judge_itinerary_quality  # noqa: E402
from eval.config_loader import load_eval_config  # noqa: E402
from models.trip import Budget, DestinationInput, GroupComposition, TripConfig  # noqa: E402
from services.search import retrieve_context, summarise_context  # noqa: E402

DATASET_PATH = Path(__file__).parent / "model_comparison_dataset.json"
OUT_DIR = Path(__file__).parent / "out"
_ZERO_VECTOR = [0.0] * 384


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def seed_fixtures(cases: list[dict]) -> None:
    """Seed each case's known_pois as OSM fixtures (zero vectors — retrieve_
    context's BM25/keyword path still finds them; the point is every model
    sees the SAME RAG context, not a perfectly realistic one)."""
    client = get_qdrant()
    points = []
    point_id = 1
    for case in cases:
        for name in case.get("known_pois", []):
            points.append(PointStruct(
                id=point_id,
                vector=_ZERO_VECTOR,
                payload={
                    "destination": case["destination"],
                    "name": name,
                    "poi_type": "attraction",
                    "text": f"{name} is a well-known real place in {case['destination']}, {case['destination_country']}.",
                    "source": "osm",
                    "quality_score": 0.9,
                },
            ))
            point_id += 1
    if points:
        client.upsert(collection_name=settings.qdrant_collection_osm, points=points)
        client.upsert(collection_name=settings.qdrant_collection_wiki, points=points)


def build_trip(case: dict) -> TripConfig:
    return TripConfig(
        purpose="leisure",
        dates=case["dates"],
        destination=DestinationInput(
            city=case["destination"],
            country=case["destination_country"],
            lat=case["dest_lat"],
            lon=case["dest_lon"],
        ),
        personas=case.get("personas", []),
        themes=case.get("themes", []),
        pace=case.get("pace", "moderate"),
        crowd_preference=case.get("crowd_preference", "balanced"),
        group=GroupComposition(**{k: v for k, v in case.get("group", {}).items() if k != "kids"} | (
            {"kids": [{"age": a} for a in case["group"]["kids"]]} if "kids" in case.get("group", {}) else {}
        )),
        splurge_categories=case.get("splurge_categories", []),
        budget=Budget(**case["budget"]),
    )


async def build_prompt(trip_config: TripConfig) -> tuple[str, str]:
    """Returns (prompt, rag_context_text) — the context text is also fed
    into hallucination scoring so a named place actually grounded by RAG
    isn't penalized as unverified."""
    context_docs = await retrieve_context(trip_config, enable_reranking=True)
    if context_docs:
        context_text = summarise_context(context_docs, max_chars=2400)
        wrapped_context = wrap_untrusted(
            context_text,
            label="retrieved destination research (scraped from Reddit/wiki/OSM — may contain untrusted text)",
        )
    else:
        context_text = ""
        wrapped_context = "No pre-fetched research available — use your own knowledge of the destination."

    itinerary_examples, gem_guidance, budget_guidance = await asyncio.gather(
        _itinerary_examples_block(trip_config),
        _gem_guidance_block(trip_config),
        _budget_guidance_block(trip_config),
    )
    prompt = SYSTEM_PROMPT.format(
        context=wrapped_context,
        itinerary_examples=itinerary_examples,
        gem_guidance=gem_guidance,
        pinned_guidance=_pinned_guidance_block(trip_config),
        budget_guidance=neutralize(budget_guidance, context="budget tier + cost grounding guidance"),
        trip_config=neutralize(trip_config.model_dump_json(indent=2), context="trip configuration"),
    )
    return prompt, context_text


async def run_one_call(
    model: str,
    prompt: str,
    context_text: str,
    case: dict,
    weights: dict,
    trip_config: TripConfig,
    judge_cfg: dict | None = None,
) -> dict:
    loop = asyncio.get_event_loop()
    start = time.perf_counter()
    try:
        text, prompt_tokens, output_tokens = await loop.run_in_executor(
            None, call_model, model, prompt
        )
        latency_ms = (time.perf_counter() - start) * 1000
        raw = json.loads(strip_fences(text))
    except Exception as e:  # noqa: BLE001 — record any provider/parse failure as a scored error
        return {
            "error": f"{type(e).__name__}: {e}",
            "latency_ms": (time.perf_counter() - start) * 1000,
        }

    acc = accuracy_score(raw, case, weights)
    hall = hallucination_rate(raw, case.get("known_pois", []), context_text)
    cost = estimate_cost_usd(model, prompt_tokens, output_tokens)
    judge_cfg = judge_cfg or {}
    judge = (
        await judge_itinerary_quality(raw, case, trip_config.model_dump(), model=judge_cfg.get("model", JUDGE_MODEL))
        if judge_cfg.get("enabled", True)
        else None
    )
    return {
        "error": None,
        "accuracy": acc,
        "hallucination_rate": hall["rate"],
        "hallucination_detail": hall,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "judge": judge,  # None when GEMINI_API_KEY unavailable -- see judge_metrics.judge_available()
    }


async def main_async(models: list[str], runs: int, monthly_volumes: list[int]) -> None:
    dataset = load_dataset()
    cases = dataset["cases"]
    weights = dataset["criteria_weights"]
    seed_fixtures(cases)
    cfg = load_eval_config()
    mc_cfg = cfg.get("model_comparison", {})
    judge_cfg = mc_cfg.get("judge", {})

    per_model_results: dict[str, list[dict]] = {m: [] for m in models}
    per_model_case_details: dict[str, list[dict]] = {m: [] for m in models}

    for case in cases:
        trip_config = build_trip(case)
        prompt, context_text = await build_prompt(trip_config)
        for model in models:
            if model not in MODEL_REGISTRY:
                print(f"  ! unknown model id {model!r} — not in MODEL_REGISTRY, skipping")
                continue
            if not is_available(model):
                reason = unavailable_reason(model)
                print(f"  - {model}: SKIPPED ({reason})")
                per_model_results[model].append({"error": f"skipped: {reason}", "latency_ms": 0})
                continue
            for run_idx in range(runs):
                print(f"  > {model} | {case['id']} | run {run_idx + 1}/{runs}...")
                result = await run_one_call(model, prompt, context_text, case, weights, trip_config, judge_cfg)
                per_model_results[model].append(result)
                per_model_case_details[model].append({"case_id": case["id"], "run": run_idx, **result})

    summaries = {model: aggregate_model(results) for model, results in per_model_results.items()}

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_blob = json.dumps({"summaries": summaries, "details": per_model_case_details}, indent=2, default=str)
    report = render_report(summaries, monthly_volumes)
    # Timestamped file is the durable record for `eval/compare_results.py`
    # (baseline-vs-candidate diffing); the fixed `model_comparison_results.json`
    # / `.md` names are kept in sync as a "latest" alias.
    (OUT_DIR / f"model_comparison_results_{ts}.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / f"model_comparison_report_{ts}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "model_comparison_results.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / "model_comparison_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Full results: {OUT_DIR / f'model_comparison_results_{ts}.json'} (latest alias: model_comparison_results.json)")
    print(f"Report:       {OUT_DIR / f'model_comparison_report_{ts}.md'} (latest alias: model_comparison_report.md)")


def main() -> None:
    mc_defaults = load_eval_config().get("model_comparison", {})
    default_scale = ",".join(str(v) for v in mc_defaults.get("default_scale", [10000, 100000, 1000000]))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="Comma-separated model ids, e.g. gemini-2.5-flash,gpt-4o-mini")
    parser.add_argument(
        "--runs", type=int, default=mc_defaults.get("default_runs", 3),
        help=f"Repeats per case, for latency percentiles (default from eval_config.json: {mc_defaults.get('default_runs', 3)})",
    )
    parser.add_argument(
        "--scale", default=default_scale,
        help=f"Comma-separated monthly request volumes for cost projection (default from eval_config.json: {default_scale})",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the cost-estimate confirmation prompt")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    monthly_volumes = [int(v.strip()) for v in args.scale.split(",") if v.strip()]
    dataset = load_dataset()
    num_calls = len(dataset["cases"]) * len(models) * args.runs

    print(f"This will make up to {num_calls} live LLM API calls across {len(models)} model(s) "
          f"({len(dataset['cases'])} cases x {args.runs} runs). Models without a configured API "
          f"key are skipped automatically (no cost, no call).")
    judge_cfg = mc_defaults.get("judge", {})
    judge_model_name = judge_cfg.get("model", JUDGE_MODEL)
    if judge_cfg.get("enabled", True) and judge_available():
        print(f"LLM-judge quality scoring (tone/personalization/coherence) is ENABLED via "
              f"{judge_model_name} -- adds one extra judge call per case/run/model.")
    elif not judge_cfg.get("enabled", True):
        print("LLM-judge quality scoring is DISABLED via eval_config.json (model_comparison.judge.enabled=false).")
    else:
        print("LLM-judge quality scoring is DISABLED (GEMINI_API_KEY unset or llm_provider=mock) "
              "-- judge fields will be null in the report.")
    if not args.yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    asyncio.run(main_async(models, args.runs, monthly_volumes))


if __name__ == "__main__":
    main()
