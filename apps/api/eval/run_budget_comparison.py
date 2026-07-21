"""Budget-recommendation comparison eval runner (docs/eval-set.md Section 14).

Answers a concrete product question raised alongside item 10 of
docs/NEXT_SESSION_TODO.md's recalibration work: now that
`core/budget_estimator.py`'s figures are grounded in real fare/cost
anchors, how does its bare-minimum estimate actually compare to what a
user would get by just pasting their itinerary into ChatGPT/Claude/
Gemini/Kimi and asking for a budget directly? This runs each dataset
case's `user_prompt` (see eval/budget_comparison_dataset.json) against:

  - WanderPlanner's own `estimate_bare_minimum_budget()` — a local,
    deterministic, zero-cost, zero-latency-variance computation, included
    as its own row in the report for direct comparison, not as a
    privileged "ground truth" (see the dataset's `anchor_methodology`
    for the honest caveat about what its anchor numbers are and aren't).
  - Each requested LLM model (gpt-4o-mini, claude-3-5-haiku-20241022,
    gemini-2.5-flash, kimi-k2-0711-preview by default), called with
    `json_mode=False` via eval/llm_providers.call_model so each returns
    ordinary conversational prose, not a forced JSON blob no real end
    user asking a chatbot a question would ever see.

Scores (see budget_comparison_scoring.py):
    anchor_adherence           — how close the extracted total lands to
                                  WanderPlanner's own real-anchor-grounded
                                  estimate (directional, not ground truth)
    no_answer_rate             — how often no usable number could even be
                                  extracted from the response
    clarifying_question_rate   — did the model ask for info this dataset's
                                  prompts already supply (a false-positive
                                  stall, recorded not scored good/bad)
    breakdown_rate             — did the response separate flights/stay/food
    hedge_language_rate        — did the response use uncertainty language
    run-to-run variance        — coefficient of variation across --runs
                                  repeats of the SAME prompt (WanderPlanner's
                                  own estimator is always exactly 0)

COSTS REAL MONEY for any LLM in --models with a configured key. Default
5 cases x 3 runs x N models. Missing API keys are NOT an error — that
model is skipped with a note, same as run_model_comparison.py.

Usage (from apps/api, venv python):
    python -m eval.run_budget_comparison --models gpt-4o-mini,claude-3-5-haiku-20241022,gemini-2.5-flash,kimi-k2-0711-preview
    python -m eval.run_budget_comparison --models gemini-2.5-flash --runs 5 --yes
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.budget_estimator import estimate_bare_minimum_budget  # noqa: E402
from core.llm_client import estimate_cost_usd  # noqa: E402
from eval.budget_comparison_scoring import (  # noqa: E402
    aggregate_model,
    coefficient_of_variation,
    render_report,
    score_one_response,
)
from eval.llm_providers import (  # noqa: E402
    MODEL_REGISTRY,
    call_model,
    is_available,
    unavailable_reason,
)

DATASET_PATH = Path(__file__).parent / "budget_comparison_dataset.json"
OUT_DIR = Path(__file__).parent / "out"
WANDERPLANNER_LABEL = "wanderplanner_estimator"


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _case_trip_config(case: dict) -> dict:
    return {
        "group": case["group"],
        "destination": case["destination"],
        "origin": case["origin"],
        "scope": case["scope"],
        "dates": case["dates"],
    }


async def run_wanderplanner(case: dict) -> dict:
    """WanderPlanner's own estimator — deterministic, so one call stands in
    for all `--runs` repeats (recorded once per run anyway, for a fair
    "calls" count in the report, since its variance is trivially 0)."""
    start = time.perf_counter()
    result = await estimate_bare_minimum_budget(_case_trip_config(case), case.get("traveller_level_hint"))
    latency_ms = (time.perf_counter() - start) * 1000
    if result is None:
        return {"error": "estimator returned None (group size unknown)", "latency_ms": latency_ms}
    total = result["total_inr"]
    scored = score_one_response(f"Total estimated budget: INR {total}. Breakdown: flights, stay, food.", case["anchor_low_inr"], case["anchor_high_inr"])
    return {
        "error": None,
        "extracted_total_inr": total,  # use the real structured number, not the regex-extracted proxy
        "anchor_adherence": scored["anchor_adherence"],
        "asked_clarifying_question": False,
        "gave_breakdown": True,
        "used_hedge_language": False,
        "latency_ms": latency_ms,
        "cost_usd": 0.0,
    }


async def run_llm_call(model: str, case: dict) -> dict:
    loop = asyncio.get_event_loop()
    start = time.perf_counter()
    try:
        text, prompt_tokens, output_tokens = await loop.run_in_executor(
            None, call_model, model, case["user_prompt"], False
        )
        latency_ms = (time.perf_counter() - start) * 1000
    except Exception as e:  # noqa: BLE001 — record any provider failure as a scored error
        return {"error": f"{type(e).__name__}: {e}", "latency_ms": (time.perf_counter() - start) * 1000}

    scored = score_one_response(text, case["anchor_low_inr"], case["anchor_high_inr"])
    cost = estimate_cost_usd(model, prompt_tokens, output_tokens)
    return {
        "error": None,
        "response_text": text,
        "latency_ms": latency_ms,
        "cost_usd": cost,
        **scored,
    }


async def main_async(models: list[str], runs: int) -> None:
    dataset = load_dataset()
    cases = dataset["cases"]
    all_models = [WANDERPLANNER_LABEL] + models

    per_model_results: dict[str, list[dict]] = {m: [] for m in all_models}
    per_model_case_details: dict[str, list[dict]] = {m: [] for m in all_models}
    case_variances: dict[str, dict[str, float | None]] = {}

    for case in cases:
        case_variances[case["id"]] = {}

        # WanderPlanner's own estimator — one deterministic call.
        result = await run_wanderplanner(case)
        per_model_results[WANDERPLANNER_LABEL].append(result)
        per_model_case_details[WANDERPLANNER_LABEL].append({"case_id": case["id"], "run": 0, **result})
        case_variances[case["id"]][WANDERPLANNER_LABEL] = 0.0 if not result.get("error") else None

        for model in models:
            if model not in MODEL_REGISTRY:
                print(f"  ! unknown model id {model!r} — not in MODEL_REGISTRY, skipping")
                continue
            if not is_available(model):
                reason = unavailable_reason(model)
                print(f"  - {model}: SKIPPED ({reason})")
                per_model_results[model].append({"error": f"skipped: {reason}", "latency_ms": 0})
                continue
            case_totals: list[float | None] = []
            for run_idx in range(runs):
                print(f"  > {model} | {case['id']} | run {run_idx + 1}/{runs}...")
                result = await run_llm_call(model, case)
                per_model_results[model].append(result)
                per_model_case_details[model].append({"case_id": case["id"], "run": run_idx, **result})
                case_totals.append(result.get("extracted_total_inr"))
            case_variances[case["id"]][model] = coefficient_of_variation(case_totals)

    summaries = {model: aggregate_model(results) for model, results in per_model_results.items()}

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_blob = json.dumps({"summaries": summaries, "details": per_model_case_details, "case_variances": case_variances}, indent=2, default=str)
    report = render_report(case_variances, summaries)
    (OUT_DIR / f"budget_comparison_results_{ts}.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / f"budget_comparison_report_{ts}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "budget_comparison_results.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / "budget_comparison_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Full results: {OUT_DIR / f'budget_comparison_results_{ts}.json'} (latest alias: budget_comparison_results.json)")
    print(f"Report:       {OUT_DIR / f'budget_comparison_report_{ts}.md'} (latest alias: budget_comparison_report.md)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--models", default="gpt-4o-mini,claude-3-5-haiku-20241022,gemini-2.5-flash,kimi-k2-0711-preview",
        help="Comma-separated model ids to compare against WanderPlanner's own estimator",
    )
    parser.add_argument("--runs", type=int, default=3, help="Repeats per case per LLM, for variance measurement")
    parser.add_argument("--yes", action="store_true", help="Skip the cost-estimate confirmation prompt")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    dataset = load_dataset()
    num_calls = len(dataset["cases"]) * len(models) * args.runs

    print(f"This will make up to {num_calls} live LLM API calls across {len(models)} model(s) "
          f"({len(dataset['cases'])} cases x {args.runs} runs), plus one local (free) call per case "
          f"to WanderPlanner's own estimator. Models without a configured API key are skipped "
          f"automatically (no cost, no call).")
    if not args.yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    asyncio.run(main_async(models, args.runs))


if __name__ == "__main__":
    main()
