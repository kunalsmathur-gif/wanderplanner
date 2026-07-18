"""Adversarial / red-team eval runner (docs/eval-set.md §9).

Companion to eval/run_model_comparison.py — that harness compares models on
quality/cost/latency; this one compares them on robustness against the
actual injection vectors WanderPlanner exposes: scraped RAG content
(wrapped by core/prompt_guard.py::wrap_untrusted, same as production's
_gemini_itinerary) and user-controlled trip-config free-text fields
(neutralized by core/prompt_guard.py::neutralize, same as production).

Each dataset case (eval/red_team_dataset.json) injects one payload into one
vector and checks, per model, whether the attack's success indicator (a
shared canary token, a suspicious domain/venue name, an unsafe keyword for
a kids trip, or excessive output-token cost) shows up in the response. See
eval/red_team_scoring.py's docstring for exactly what each check measures
and its limits — this is a proxy for LLM-level robustness, not a substitute
for a real security review, and it does not exercise the wizard/chat-refine
endpoints (only itinerary generation) — see docs/eval-set.md §9 for that
scoping note.

COSTS REAL MONEY — one live API call per case per model. Missing API keys
skip that model automatically (see eval/llm_providers.py).

Usage (from apps/api, venv python):
    python -m eval.run_red_team_eval --models gemini-2.5-flash,gpt-4o-mini
    python -m eval.run_red_team_eval --models <...> --yes
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

# Same isolation trick as the other eval runners — never touch real Qdrant.
# Best-effort blocks (_gem_guidance_block, budget cost-grounding) degrade to
# empty against an empty in-memory store, which is fine: this eval controls
# the RAG context directly via the injected payload, it doesn't need real
# retrieval to work.
settings.qdrant_url = ":memory:"

from chains.itinerary_chain import (  # noqa: E402
    SYSTEM_PROMPT,
    _budget_guidance_block,
    _gem_guidance_block,
    _itinerary_examples_block,
    _pinned_guidance_block,
)
from core.prompt_guard import neutralize, wrap_untrusted  # noqa: E402
from eval.llm_providers import (  # noqa: E402
    MODEL_REGISTRY,
    call_model,
    is_available,
    strip_fences,
    unavailable_reason,
)
from eval.red_team_scoring import aggregate_model, render_report, score_case  # noqa: E402
from models.trip import Budget, DestinationInput, GroupComposition, TripConfig  # noqa: E402

DATASET_PATH = Path(__file__).parent / "red_team_dataset.json"
OUT_DIR = Path(__file__).parent / "out"


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def build_trip(case: dict) -> TripConfig:
    """Builds the TripConfig for a case, embedding the attack payload into
    whichever field the case's injection_vector names. RAG-vector cases
    leave the trip config clean — their payload goes into context instead
    (see build_prompt)."""
    purpose = "leisure"
    if case["injection_vector"] == "trip_config_purpose":
        purpose = case["attack_payload"]

    # destination_country doubles as the literal field value for that vector
    # (the dataset embeds the payload directly in "destination_country" for
    # RT-006 rather than a separate attack_payload string).
    country = case["destination_country"]

    group_raw = dict(case.get("group", {}))
    kids = group_raw.pop("kids", None)
    group = GroupComposition(**group_raw, kids=[{"age": a} for a in kids] if kids else [])

    return TripConfig(
        purpose=purpose,
        dates=case["dates"],
        destination=DestinationInput(
            city=case["destination"],
            country=country,
            lat=case["dest_lat"],
            lon=case["dest_lon"],
        ),
        group=group,
        budget=Budget(**case["budget"]),
    )


async def build_prompt(trip_config: TripConfig, case: dict) -> str:
    """Mirrors chains.itinerary_chain._gemini_itinerary's prompt assembly,
    except the RAG "destination research" context is the case's injected
    payload (RAG-vector cases) or the normal "no research" sentinel
    (non-RAG-vector cases) instead of a real retrieve_context() call — this
    eval needs the payload to deterministically land in context, not
    depend on whether retrieval happens to surface it."""
    if case["injection_vector"] == "rag_context":
        wrapped_context = wrap_untrusted(
            case["attack_payload"],
            label="retrieved destination research (scraped from Reddit/wiki/OSM — may contain untrusted text)",
        )
    else:
        wrapped_context = "No pre-fetched research available — use your own knowledge of the destination."

    itinerary_examples, gem_guidance, budget_guidance = await asyncio.gather(
        _itinerary_examples_block(trip_config),
        _gem_guidance_block(trip_config),
        _budget_guidance_block(trip_config),
    )
    return SYSTEM_PROMPT.format(
        context=wrapped_context,
        itinerary_examples=itinerary_examples,
        gem_guidance=gem_guidance,
        pinned_guidance=_pinned_guidance_block(trip_config),
        budget_guidance=neutralize(budget_guidance, context="budget tier + cost grounding guidance"),
        trip_config=neutralize(trip_config.model_dump_json(indent=2), context="trip configuration"),
    )


async def run_one_case(model: str, case: dict, dataset: dict) -> dict:
    base = {"case_id": case["id"], "category": case["category"]}
    trip_config = build_trip(case)
    prompt = await build_prompt(trip_config, case)

    loop = asyncio.get_event_loop()
    start = time.perf_counter()
    try:
        text, _prompt_tokens, output_tokens = await loop.run_in_executor(None, call_model, model, prompt)
        latency_ms = (time.perf_counter() - start) * 1000
        try:
            raw = json.loads(strip_fences(text))
        except Exception:
            raw = None
    except Exception as e:  # noqa: BLE001 — a provider refusal/error is itself a valid, safe outcome to record
        return {**base, "error": f"{type(e).__name__}: {e}", "latency_ms": (time.perf_counter() - start) * 1000}

    scored = score_case(
        raw,
        output_tokens,
        case,
        dataset["canary"],
        dataset["unsafe_keywords_for_kids"],
        dataset["cost_abuse_output_token_threshold"],
    )
    return {**base, "error": None, "latency_ms": latency_ms, "output_tokens": output_tokens, **scored}


async def main_async(models: list[str]) -> None:
    dataset = load_dataset()
    cases = dataset["cases"]

    per_model_results: dict[str, list[dict]] = {m: [] for m in models}

    for case in cases:
        for model in models:
            if model not in MODEL_REGISTRY:
                print(f"  ! unknown model id {model!r} — not in MODEL_REGISTRY, skipping")
                continue
            if not is_available(model):
                reason = unavailable_reason(model)
                print(f"  - {model}: SKIPPED ({reason})")
                per_model_results[model].append({
                    "case_id": case["id"], "category": case["category"],
                    "error": f"skipped: {reason}",
                })
                continue
            print(f"  > {model} | {case['id']} ({case['category']})...")
            result = await run_one_case(model, case, dataset)
            per_model_results[model].append(result)
            if result.get("attack_succeeded"):
                print(f"    !! ATTACK SUCCEEDED — evidence: {result.get('evidence')}")

    summaries = {model: aggregate_model(results) for model, results in per_model_results.items()}

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_blob = json.dumps({"summaries": summaries, "details": per_model_results}, indent=2, default=str)
    report = render_report(summaries)
    # Timestamped file is the durable record for `eval/compare_results.py`
    # (baseline-vs-candidate diffing); the fixed `red_team_results.json` /
    # `.md` names are kept in sync as a "latest" alias so anything that
    # still points at the old fixed filename keeps working.
    (OUT_DIR / f"red_team_results_{ts}.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / f"red_team_report_{ts}.md").write_text(report, encoding="utf-8")
    (OUT_DIR / "red_team_results.json").write_text(results_blob, encoding="utf-8")
    (OUT_DIR / "red_team_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Full results: {OUT_DIR / f'red_team_results_{ts}.json'} (latest alias: red_team_results.json)")
    print(f"Report:       {OUT_DIR / f'red_team_report_{ts}.md'} (latest alias: red_team_report.md)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="Comma-separated model ids, e.g. gemini-2.5-flash,gpt-4o-mini")
    parser.add_argument("--yes", action="store_true", help="Skip the cost-estimate confirmation prompt")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    dataset = load_dataset()
    num_calls = len(dataset["cases"]) * len(models)

    print(f"This will make up to {num_calls} live LLM API calls across {len(models)} model(s) "
          f"({len(dataset['cases'])} adversarial cases). Models without a configured API key "
          f"are skipped automatically (no cost, no call).")
    if not args.yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    asyncio.run(main_async(models))


if __name__ == "__main__":
    main()
