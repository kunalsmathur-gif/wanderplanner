"""Scoring for the LLM model-selection eval (docs/eval-set.md §8).

Built to answer a concrete question — "should we run MMLU/GPQA to decide
which LLM (currently Gemini 2.5) WanderPlanner should use?" — with "no,
those benchmarks don't measure anything this product actually depends on."
Instead this scores the REAL production itinerary prompt/response shape on
five axes:

    accuracy        — schema_valid, day_count_match, theme_coverage,
                       budget_adherence (weighted per criteria_weights in
                       model_comparison_dataset.json)
    hallucination    — proxy rate: fraction of named items that match
                       NEITHER the case's curated `known_pois` whitelist NOR
                       the retrieved RAG context text, using the same fuzzy
                       matcher production POI-pinning uses
                       (services.poi_pinning._names_match). This is an upper
                       bound, not ground truth — small real venues genuinely
                       absent from both sources will be flagged too — but
                       run identically across all candidate models it is a
                       fair *relative* ranking signal.
    latency          — wall-clock per call, aggregated to p50/p95
    token cost       — from provider usage metadata + core.llm_client
                       pricing table (approximate public list pricing)
    scale cost       — token cost projected across configurable monthly
                       request volumes

Pure functions over plain dicts so the runner, tests, and any future
baseline comparison share one definition of each metric.
"""
from __future__ import annotations

import statistics
from typing import Any

from services.poi_pinning import _names_match, _normalize

# Words too generic to count as a "named place" for hallucination purposes —
# without this filter, ordinary activity titles ("Free morning", "Lunch
# break") would be flagged as unverified proper nouns.
_GENERIC_TITLE_WORDS = {
    "lunch", "dinner", "breakfast", "free", "morning", "afternoon", "evening",
    "check-in", "check-out", "departure", "arrival", "transfer", "rest",
    "leisure", "optional", "return", "flight", "travel", "day",
}


def _looks_like_named_place(title: str) -> bool:
    t = title.strip().lower()
    if not t:
        return False
    return not any(word in t for word in _GENERIC_TITLE_WORDS) and len(t) >= 4


# ---------------------------------------------------------------------------
# Schema validity — stricter than the production parser (chains.itinerary_
# chain._parse_days silently defaults missing fields; this eval wants to
# know when a model actually omitted them).
# ---------------------------------------------------------------------------

REQUIRED_ITEM_FIELDS = ("title", "description", "time_start", "time_end", "location")
REQUIRED_LOCATION_FIELDS = ("lat", "lon")


def validate_schema(raw: dict) -> tuple[bool, list[str]]:
    """Returns (is_valid, list_of_issues). Does not raise."""
    issues: list[str] = []
    if not isinstance(raw, dict):
        return False, ["response is not a JSON object"]
    days = raw.get("days")
    if not isinstance(days, list) or not days:
        return False, ["missing or empty 'days' array"]
    for i, day in enumerate(days):
        if not isinstance(day, dict):
            issues.append(f"day[{i}] is not an object")
            continue
        items = day.get("items")
        if not isinstance(items, list) or not items:
            issues.append(f"day[{i}] missing or empty 'items'")
            continue
        for j, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append(f"day[{i}].items[{j}] is not an object")
                continue
            for field in REQUIRED_ITEM_FIELDS:
                if field not in item:
                    issues.append(f"day[{i}].items[{j}] missing '{field}'")
            loc = item.get("location")
            if isinstance(loc, dict):
                for field in REQUIRED_LOCATION_FIELDS:
                    if field not in loc:
                        issues.append(f"day[{i}].items[{j}].location missing '{field}'")
    return (len(issues) == 0), issues


# ---------------------------------------------------------------------------
# Accuracy sub-scores
# ---------------------------------------------------------------------------

def day_count_match(raw: dict, expected_num_days: int) -> float:
    days = raw.get("days") or []
    actual = len(days)
    if expected_num_days <= 0:
        return 1.0
    diff = abs(actual - expected_num_days)
    return max(0.0, 1.0 - diff / expected_num_days)


def theme_coverage(raw: dict, required_theme_keywords: list[str]) -> float:
    """Fraction of required keywords found (case-insensitive substring) in
    any item's title/description/tags across the whole itinerary."""
    if not required_theme_keywords:
        return 1.0
    haystack_parts: list[str] = []
    for day in raw.get("days") or []:
        for item in day.get("items") or []:
            haystack_parts.append(str(item.get("title", "")))
            haystack_parts.append(str(item.get("description", "")))
            haystack_parts.extend(str(t) for t in (item.get("tags") or []))
    haystack = " ".join(haystack_parts).lower()
    hits = sum(1 for kw in required_theme_keywords if kw.lower() in haystack)
    return hits / len(required_theme_keywords)


def budget_adherence(raw: dict, budget_amount: float) -> float:
    """1.0 if estimated total spend is within budget (or budget unset), decaying
    linearly to 0 at 2x budget. expense_breakdown values are in INR per
    models.itinerary.ExpenseBreakdown; the case's budget is also authored in
    INR to avoid a currency-conversion assumption inside the eval itself."""
    if budget_amount <= 0:
        return 1.0
    breakdown = raw.get("expense_breakdown") or {}
    total = sum(v for k, v in breakdown.items() if isinstance(v, (int, float)))
    if total <= 0:
        return 0.5  # model didn't provide a breakdown — partial credit, not a hard fail
    ratio = total / budget_amount
    if ratio <= 1.0:
        return 1.0
    if ratio >= 2.0:
        return 0.0
    return 1.0 - (ratio - 1.0)


def accuracy_score(raw: dict, case: dict, weights: dict[str, float]) -> dict[str, float]:
    is_valid, _issues = validate_schema(raw)
    schema_component = 1.0 if is_valid else 0.0
    days_component = day_count_match(raw, case["expected_num_days"])
    theme_component = theme_coverage(raw, case.get("required_theme_keywords") or [])
    budget_component = budget_adherence(raw, case.get("budget", {}).get("amount", 0))
    overall = (
        weights.get("schema_valid", 0.25) * schema_component
        + weights.get("day_count_match", 0.25) * days_component
        + weights.get("theme_coverage", 0.25) * theme_component
        + weights.get("budget_adherence", 0.25) * budget_component
    )
    return {
        "schema_valid": schema_component,
        "day_count_match": days_component,
        "theme_coverage": theme_component,
        "budget_adherence": budget_component,
        "overall": round(overall, 4),
    }


# ---------------------------------------------------------------------------
# Hallucination proxy rate
# ---------------------------------------------------------------------------

def hallucination_rate(raw: dict, known_pois: list[str], rag_context_text: str) -> dict[str, Any]:
    """See module docstring for the "proxy, not ground truth" caveat."""
    known_norms = [_normalize(p) for p in known_pois]
    context_norm = _normalize(rag_context_text)

    named_titles: list[str] = []
    for day in raw.get("days") or []:
        for item in day.get("items") or []:
            title = str(item.get("title", ""))
            if _looks_like_named_place(title):
                named_titles.append(title)

    if not named_titles:
        return {"rate": 0.0, "named_count": 0, "unverified": []}

    unverified = []
    for title in named_titles:
        title_norm = _normalize(title)
        matches_known = any(_names_match(title_norm, k) for k in known_norms)
        matches_context = len(title_norm) >= 6 and title_norm in context_norm
        if not matches_known and not matches_context:
            unverified.append(title)

    return {
        "rate": round(len(unverified) / len(named_titles), 4),
        "named_count": len(named_titles),
        "unverified": unverified,
    }


# ---------------------------------------------------------------------------
# Aggregation across cases/runs, per model
# ---------------------------------------------------------------------------

def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(pct / 100 * (len(s) - 1)))))
    return s[idx]


def aggregate_model(results: list[dict]) -> dict:
    """`results` is a list of per-call records for one model:
    {accuracy: {...overall...}, hallucination_rate, latency_ms,
     prompt_tokens, output_tokens, cost_usd, error: str|None}."""
    ok = [r for r in results if not r.get("error")]
    errored = [r for r in results if r.get("error")]
    if not ok:
        return {
            "calls": len(results),
            "errors": len(errored),
            "error_rate": 1.0 if results else 0.0,
        }
    accuracies = [r["accuracy"]["overall"] for r in ok]
    hallucinations = [r["hallucination_rate"] for r in ok]
    latencies = [r["latency_ms"] for r in ok]
    costs = [r["cost_usd"] for r in ok]
    prompt_tokens = [r["prompt_tokens"] for r in ok]
    output_tokens = [r["output_tokens"] for r in ok]
    return {
        "calls": len(results),
        "errors": len(errored),
        "error_rate": round(len(errored) / len(results), 4) if results else 0.0,
        "accuracy_mean": round(statistics.mean(accuracies), 4),
        "hallucination_rate_mean": round(statistics.mean(hallucinations), 4),
        "latency_ms_p50": round(_percentile(latencies, 50), 1),
        "latency_ms_p95": round(_percentile(latencies, 95), 1),
        "cost_usd_mean_per_request": round(statistics.mean(costs), 6),
        "prompt_tokens_mean": round(statistics.mean(prompt_tokens), 1),
        "output_tokens_mean": round(statistics.mean(output_tokens), 1),
    }


def project_scale_cost(cost_usd_mean_per_request: float, monthly_volumes: list[int]) -> dict[str, float]:
    return {
        f"{vol:,}_requests_per_month": round(cost_usd_mean_per_request * vol, 2)
        for vol in monthly_volumes
    }


def render_report(model_summaries: dict[str, dict], monthly_volumes: list[int]) -> str:
    lines = [
        "# WanderPlanner — LLM Model-Selection Eval Report",
        "",
        "Compares candidate models on the REAL production itinerary prompt/RAG",
        "context (not MMLU/GPQA — see docs/eval-set.md §8 for why). Hallucination",
        "rate is a proxy (see model_comparison_scoring.py docstring).",
        "",
        "| Model | Accuracy | Hallucination Rate | p50 Latency (ms) | p95 Latency (ms) | Cost/Request (USD) | Error Rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, summary in model_summaries.items():
        if "accuracy_mean" not in summary:
            lines.append(f"| {model} | SKIPPED/FAILED ({summary.get('errors', 0)} errors) | - | - | - | - | {summary.get('error_rate', 1.0)} |")
            continue
        lines.append(
            f"| {model} | {summary['accuracy_mean']} | {summary['hallucination_rate_mean']} | "
            f"{summary['latency_ms_p50']} | {summary['latency_ms_p95']} | "
            f"{summary['cost_usd_mean_per_request']} | {summary['error_rate']} |"
        )
    lines.append("")
    lines.append("## Projected cost at scale (USD/month)")
    lines.append("")
    header = "| Model | " + " | ".join(f"{v:,} req/mo" for v in monthly_volumes) + " |"
    sep = "|---|" + "---|" * len(monthly_volumes)
    lines.append(header)
    lines.append(sep)
    for model, summary in model_summaries.items():
        if "cost_usd_mean_per_request" not in summary:
            lines.append(f"| {model} | " + " | ".join("-" for _ in monthly_volumes) + " |")
            continue
        projected = project_scale_cost(summary["cost_usd_mean_per_request"], monthly_volumes)
        lines.append(f"| {model} | " + " | ".join(str(v) for v in projected.values()) + " |")
    return "\n".join(lines) + "\n"
