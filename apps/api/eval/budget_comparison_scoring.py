"""Scoring for the budget-recommendation comparison eval (docs/eval-set.md
Section 14).

WanderPlanner's own `core/budget_estimator.py` deliberately refuses to
quote a number until group size + departure city are known, and always
returns a structured flights/stay/food breakdown grounded in real
fare/cost anchors (see that module's docstring and
`eval/budget_comparison_dataset.json`'s `anchor_methodology`). This module
scores whether a general-purpose chatbot (asked the same question a real
user would type, with none of that scaffolding) does the same things, or
just confidently guesses a number:

    anchor_adherence         — how close the LLM's extracted total lands to
                                our own real-anchor-grounded estimate (see
                                dataset's `anchor_methodology` caveat — a
                                directional signal, not ground truth)
    asked_clarifying_question — did the model ask for missing info (it
                                wasn't missing in this dataset's prompts —
                                all cases already supply group size,
                                departure city, and dates — so a "yes" here
                                is a *false positive* stall, not a virtue;
                                recorded for completeness, not scored as
                                good or bad)
    gave_breakdown            — did the response separate flights/stay/food
                                (or similar categories) rather than a single
                                bare number
    hedge_language            — did the response include uncertainty
                                language ("approximately", "around",
                                "roughly", "can vary", "depending on") —
                                the honest thing to do given neither this
                                harness nor the model has live fare data
    run_to_run_variance       — coefficient of variation of the extracted
                                total across repeated calls at temperature
                                0.4 (WanderPlanner's own estimator has zero
                                variance by construction — same inputs,
                                same deterministic arithmetic, every time)

Pure functions over plain strings/dicts, same "shared definition across
runner + tests" pattern as `model_comparison_scoring.py`.
"""
from __future__ import annotations

import re
import statistics
from typing import Any

# ---------------------------------------------------------------------------
# Total-figure extraction — deliberately blunter than
# core/price_extraction.py's per-snippet extractor: a chatbot's answer is a
# handful of sentences, not hundreds of scraped posts, so "take the median
# of many mentions" doesn't apply. Instead this looks for an explicit
# "total" figure first (the far more reliable signal when present), and
# falls back to the largest plausible INR amount mentioned anywhere in the
# response (a breakdown's total is usually also its biggest number).
# ---------------------------------------------------------------------------

_FX_TO_INR: dict[str, float] = {
    "$": 87.0, "usd": 87.0, "us$": 87.0,
    "€": 93.0, "eur": 93.0,
    "£": 110.0, "gbp": 110.0,
    "₹": 1.0, "rs": 1.0, "rs.": 1.0, "inr": 1.0,
}

_AMOUNT_RE = re.compile(
    r"(₹|\$|€|£|Rs\.?|INR|USD|EUR|GBP)\s?([\d,]+(?:\.\d+)?)\s?(lakh|k|thousand)?",
    re.IGNORECASE,
)

_TOTAL_LINE_RE = re.compile(
    r"(?:^|\n|\. )[^\n.]{0,40}\btotal\b[^\n.]{0,60}?"
    r"(₹|\$|€|£|Rs\.?|INR|USD|EUR|GBP)\s?([\d,]+(?:\.\d+)?)\s?(lakh|k|thousand)?",
    re.IGNORECASE,
)

# Sanity bounds for a whole-trip (not per-night) total — anything outside
# this is almost certainly a misparsed unit price (e.g. a per-night hotel
# rate), not the trip total.
_TOTAL_BOUNDS_INR = (5_000, 5_000_000)


def _to_inr(symbol: str, raw_amount: str, multiplier_word: str | None) -> float | None:
    try:
        amount = float(raw_amount.replace(",", ""))
    except ValueError:
        return None
    rate = _FX_TO_INR.get(symbol.lower().rstrip("."))
    if rate is None:
        return None
    if multiplier_word:
        word = multiplier_word.lower()
        if word == "lakh":
            amount *= 100_000
        elif word in ("k", "thousand"):
            amount *= 1_000
    return amount * rate


def extract_total_inr(text: str) -> float | None:
    """Best-effort extraction of the response's headline total trip cost, in
    INR. Returns None if nothing plausible is found (the model gave no
    number at all, e.g. it only asked clarifying questions)."""
    if not text:
        return None

    # Prefer an explicit "total" mention.
    totals: list[float] = []
    for symbol, raw_amount, multiplier in _TOTAL_LINE_RE.findall(text):
        inr = _to_inr(symbol, raw_amount, multiplier or None)
        if inr is not None and _TOTAL_BOUNDS_INR[0] <= inr <= _TOTAL_BOUNDS_INR[1]:
            totals.append(inr)
    if totals:
        return max(totals)

    # Fall back to the largest plausible amount anywhere in the response.
    all_amounts: list[float] = []
    for symbol, raw_amount, multiplier in _AMOUNT_RE.findall(text):
        inr = _to_inr(symbol, raw_amount, multiplier or None)
        if inr is not None and _TOTAL_BOUNDS_INR[0] <= inr <= _TOTAL_BOUNDS_INR[1]:
            all_amounts.append(inr)
    if not all_amounts:
        return None
    return max(all_amounts)


# ---------------------------------------------------------------------------
# Behavioural checks — no ground truth needed, pure text heuristics.
# ---------------------------------------------------------------------------

_CLARIFYING_PATTERNS = [
    r"how many (people|adults|travellers|travelers)",
    r"which city (are you|will you be)",
    r"what (city|airport) (are you|will you be) (flying|departing|leaving) from",
    r"what dates",
    r"could you (tell me|clarify|confirm|share)",
    r"can you (tell me|clarify|confirm|share)",
    r"before i (can )?(give|provide|estimate)",
]

_BREAKDOWN_KEYWORDS = ["flight", "hotel", "accommodation", "stay", "food", "meal", "dining"]

_HEDGE_PATTERNS = [
    r"\bapproximat\w*\b", r"\baround\b", r"\broughly\b", r"\bcan vary\b", r"\bdepending on\b",
    r"\bestimate\w*\b", r"\bball\s?park\b", r"\bmay vary\b", r"\bplease note\b", r"\bthese (figures|prices|numbers)",
]


def asked_clarifying_question(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _CLARIFYING_PATTERNS)


def gave_breakdown(text: str) -> bool:
    """True if the response separates spend into at least 2 of the 3
    flights/stay/food categories, rather than one bare number."""
    if not text:
        return False
    lowered = text.lower()
    categories_hit = 0
    if any(k in lowered for k in ("flight", "airfare", "flights")):
        categories_hit += 1
    if any(k in lowered for k in ("hotel", "accommodation", "stay", "lodging")):
        categories_hit += 1
    if any(k in lowered for k in ("food", "meal", "dining", "restaurant")):
        categories_hit += 1
    return categories_hit >= 2


def used_hedge_language(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _HEDGE_PATTERNS)


def anchor_adherence(total_inr: float | None, anchor_low: float, anchor_high: float) -> float:
    """1.0 if the extracted total falls within [anchor_low, anchor_high],
    decaying linearly to 0 at 2x the nearest boundary. None (no number
    extracted at all) scores 0.0 — a non-answer is not partial credit here,
    unlike model_comparison_scoring.budget_adherence's 0.5 for "no
    breakdown" (that case still produced usable itinerary output; a budget
    eval with no number at all is a harder miss)."""
    if total_inr is None:
        return 0.0
    if anchor_low <= total_inr <= anchor_high:
        return 1.0
    if total_inr < anchor_low:
        if anchor_low <= 0:
            return 0.0
        ratio = total_inr / anchor_low
        return max(0.0, ratio)  # linear 0 -> 1 as it approaches the low bound
    # total_inr > anchor_high
    ratio = total_inr / anchor_high
    return max(0.0, 1.0 - (ratio - 1.0))  # linear 1 -> 0 by 2x the high bound


def coefficient_of_variation(values: list[float]) -> float | None:
    """Population coefficient of variation (stdev/mean) across repeated
    calls for the SAME prompt — WanderPlanner's own estimator is exactly 0
    here by construction. None if fewer than 2 non-null values."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    mean = statistics.mean(clean)
    if mean == 0:
        return None
    return round(statistics.pstdev(clean) / mean, 4)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def score_one_response(text: str, anchor_low: float, anchor_high: float) -> dict[str, Any]:
    total = extract_total_inr(text)
    return {
        "extracted_total_inr": total,
        "anchor_adherence": round(anchor_adherence(total, anchor_low, anchor_high), 4),
        "asked_clarifying_question": asked_clarifying_question(text),
        "gave_breakdown": gave_breakdown(text),
        "used_hedge_language": used_hedge_language(text),
    }


def aggregate_model(results: list[dict]) -> dict:
    """`results` is a list of per-call records for one model/estimator:
    {extracted_total_inr, anchor_adherence, asked_clarifying_question,
     gave_breakdown, used_hedge_language, latency_ms, cost_usd, error}
    across all cases and repeats."""
    ok = [r for r in results if not r.get("error")]
    errored = [r for r in results if r.get("error")]
    if not ok:
        return {"calls": len(results), "errors": len(errored), "error_rate": 1.0 if results else 0.0}

    totals = [r["extracted_total_inr"] for r in ok]
    no_answer_rate = round(sum(1 for t in totals if t is None) / len(totals), 4)
    adherences = [r["anchor_adherence"] for r in ok]
    latencies = [r["latency_ms"] for r in ok if r.get("latency_ms") is not None]
    costs = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]

    summary = {
        "calls": len(results),
        "errors": len(errored),
        "error_rate": round(len(errored) / len(results), 4) if results else 0.0,
        "no_answer_rate": no_answer_rate,
        "anchor_adherence_mean": round(statistics.mean(adherences), 4),
        "clarifying_question_rate": round(sum(1 for r in ok if r["asked_clarifying_question"]) / len(ok), 4),
        "breakdown_rate": round(sum(1 for r in ok if r["gave_breakdown"]) / len(ok), 4),
        "hedge_language_rate": round(sum(1 for r in ok if r["used_hedge_language"]) / len(ok), 4),
    }
    if latencies:
        summary["latency_ms_mean"] = round(statistics.mean(latencies), 1)
    if costs:
        summary["cost_usd_mean_per_request"] = round(statistics.mean(costs), 6)
    return summary


def render_report(case_variances: dict[str, dict[str, float | None]], model_summaries: dict[str, dict]) -> str:
    lines = [
        "# WanderPlanner — Budget-Recommendation Comparison Eval Report",
        "",
        "Compares WanderPlanner's own deterministic bare-minimum budget estimator",
        "(core/budget_estimator.py) against asking general-purpose LLMs the SAME",
        "trip question a real user would type directly (no system prompt, no RAG",
        "context, no structured-output constraint). See",
        "eval/budget_comparison_dataset.json's `anchor_methodology` for what",
        "`anchor_adherence` does and does not prove.",
        "",
        "| Model | No-Answer Rate | Anchor Adherence | Clarifying-Question Rate | Breakdown Rate | Hedge-Language Rate | Error Rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, summary in model_summaries.items():
        if "anchor_adherence_mean" not in summary:
            lines.append(f"| {model} | - | SKIPPED/FAILED ({summary.get('errors', 0)} errors) | - | - | - | {summary.get('error_rate', 1.0)} |")
            continue
        lines.append(
            f"| {model} | {summary['no_answer_rate']} | {summary['anchor_adherence_mean']} | "
            f"{summary['clarifying_question_rate']} | {summary['breakdown_rate']} | "
            f"{summary['hedge_language_rate']} | {summary['error_rate']} |"
        )
    lines.append("")
    lines.append("## Run-to-run variance per case (coefficient of variation of extracted total; WanderPlanner's own estimator is always 0.0 by construction)")
    lines.append("")
    models = list(model_summaries.keys())
    lines.append("| Case | " + " | ".join(models) + " |")
    lines.append("|---|" + "---|" * len(models))
    for case_id, per_model_cv in case_variances.items():
        row = [case_id] + [
            ("n/a" if per_model_cv.get(m) is None else str(per_model_cv[m])) for m in models
        ]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"
