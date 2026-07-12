"""Scoring for the refinement-fidelity eval (GTM Phase 1 kill-criterion gate).

Pure functions over plain data (lists of place-name strings + itinerary items
as {"title", "tags"} dicts) so the runner, the ChatGPT-baseline scorer, and
the unit tests all share one set of definitions. Name matching deliberately
reuses services/poi_pinning's normalization + fuzzy matcher — the eval must
agree with production about when two names refer to the same place.

Per positive case (expected verified POIs exist at the destination):
    expansion_recall  — expected POIs proposed by interest expansion / expected
    pin_recall        — expected POIs that became pins / expected
    pin_precision     — pins matching an expected POI / all pins
    inclusion_rate    — pins appearing EXACTLY ONCE in the itinerary with the
                        "pinned" tag / all pins (the hard-constraint contract)
    stability_rate    — pins still present after an unrelated second
                        refinement + regeneration / all pins (diff fidelity)
    fidelity          — 0.4*pin_recall + 0.4*inclusion_rate + 0.2*stability_rate

Per negative case (the honest answer is to pin nothing):
    honest            — True iff zero pins AND no unverified candidate name
                        leaked into the itinerary.

Baseline (recorded ChatGPT answers, same prompts):
    verified_recall    — expected POIs among the places it named / expected
    unverifiable_rate  — places it named matching NO fixture for that
                         destination / places named (unverifiable suggestions)
    honest             — for negative cases: named no places at all.
"""
from __future__ import annotations

import statistics
from typing import Any

from services.poi_pinning import _names_match, _normalize

Item = dict[str, Any]  # {"title": str, "tags": list[str]}


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

def matched_references(output_names: list[str], reference_names: list[str]) -> set[str]:
    """Subset of reference_names that at least one output name refers to,
    using the production fuzzy matcher."""
    matched: set[str] = set()
    for ref in reference_names:
        ref_norm = _normalize(ref)
        if any(_names_match(_normalize(out), ref_norm) for out in output_names):
            matched.add(ref)
    return matched


def _title_occurrences(name: str, items: list[Item], require_pinned_tag: bool) -> int:
    name_norm = _normalize(name)
    count = 0
    for item in items:
        if require_pinned_tag and "pinned" not in (item.get("tags") or []):
            continue
        if _names_match(_normalize(item.get("title") or ""), name_norm):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Case scoring
# ---------------------------------------------------------------------------

def score_positive_case(
    case: dict,
    candidates: list[str],
    pin_names: list[str],
    itinerary_items: list[Item],
    refined_items: list[Item],
) -> dict:
    expected = case["expected_pois"]

    expansion_recall = len(matched_references(candidates, expected)) / len(expected)
    pin_recall = len(matched_references(pin_names, expected)) / len(expected)
    on_target = sum(1 for p in pin_names if matched_references([p], expected))
    pin_precision = on_target / len(pin_names) if pin_names else 0.0

    if pin_names:
        included = sum(
            1 for p in pin_names
            if _title_occurrences(p, itinerary_items, require_pinned_tag=True) == 1
        )
        inclusion_rate = included / len(pin_names)
        surviving = sum(
            1 for p in pin_names
            if _title_occurrences(p, refined_items, require_pinned_tag=False) >= 1
        )
        stability_rate = surviving / len(pin_names)
    else:
        inclusion_rate = 0.0
        stability_rate = 0.0

    fidelity = 0.4 * pin_recall + 0.4 * inclusion_rate + 0.2 * stability_rate

    return {
        "id": case["id"],
        "destination": case["destination"],
        "interest": case["named_interest"],
        "negative": False,
        "expansion_recall": expansion_recall,
        "pin_recall": pin_recall,
        "pin_precision": pin_precision,
        "inclusion_rate": inclusion_rate,
        "stability_rate": stability_rate,
        "fidelity": fidelity,
        "pins": list(pin_names),
    }


def score_negative_case(
    case: dict,
    pin_names: list[str],
    itinerary_items: list[Item],
) -> dict:
    """Honesty check: nothing pinned, and no unverified candidate name leaked
    into the generated itinerary anyway."""
    leaked = [
        c for c in case.get("offline_candidates", [])
        if _title_occurrences(c, itinerary_items, require_pinned_tag=False) > 0
    ]
    honest = not pin_names and not leaked
    return {
        "id": case["id"],
        "destination": case["destination"],
        "interest": case["named_interest"],
        "negative": True,
        "honest": honest,
        "pins": list(pin_names),
        "leaked": leaked,
    }


def score_baseline_case(case: dict, places: list[str], fixture_names: list[str]) -> dict:
    """Score a recorded competitor answer (list of place names it suggested)
    with the same matcher. fixture_names = every fixture place (expected +
    distractors) at this case's destination — a suggestion matching none of
    them is unverifiable against our truth-set."""
    if case["negative"]:
        return {
            "id": case["id"],
            "negative": True,
            "honest": len(places) == 0,
            "places": list(places),
        }

    expected = case["expected_pois"]
    verified_recall = len(matched_references(places, expected)) / len(expected)
    if places:
        unverifiable = sum(1 for p in places if not matched_references([p], fixture_names))
        unverifiable_rate = unverifiable / len(places)
    else:
        unverifiable_rate = 0.0
    return {
        "id": case["id"],
        "negative": False,
        "verified_recall": verified_recall,
        "unverifiable_rate": unverifiable_rate,
        "places": list(places),
    }


# ---------------------------------------------------------------------------
# Aggregation + report
# ---------------------------------------------------------------------------

def _mean(results: list[dict], key: str) -> float:
    vals = [r[key] for r in results if key in r]
    return statistics.mean(vals) if vals else 0.0


def aggregate(results: list[dict]) -> dict:
    positives = [r for r in results if not r["negative"]]
    negatives = [r for r in results if r["negative"]]
    return {
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "expansion_recall": _mean(positives, "expansion_recall"),
        "pin_recall": _mean(positives, "pin_recall"),
        "pin_precision": _mean(positives, "pin_precision"),
        "inclusion_rate": _mean(positives, "inclusion_rate"),
        "stability_rate": _mean(positives, "stability_rate"),
        "fidelity": _mean(positives, "fidelity"),
        "honesty_rate": (
            sum(1 for r in negatives if r["honest"]) / len(negatives) if negatives else 1.0
        ),
    }


def aggregate_baseline(results: list[dict]) -> dict:
    positives = [r for r in results if not r["negative"]]
    negatives = [r for r in results if r["negative"]]
    return {
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "verified_recall": _mean(positives, "verified_recall"),
        "unverifiable_rate": _mean(positives, "unverifiable_rate"),
        "honesty_rate": (
            sum(1 for r in negatives if r["honest"]) / len(negatives) if negatives else 1.0
        ),
    }


def render_report(
    results: list[dict],
    agg: dict,
    mode: str,
    baseline_results: list[dict] | None = None,
    baseline_agg: dict | None = None,
) -> str:
    """Markdown report — doubles as the raw material for the published
    'WanderPlanner vs ChatGPT' comparison (GTM_STRATEGY §3 item 5)."""
    lines = [
        "# Refinement-Fidelity Eval Report",
        "",
        f"Mode: **{mode}** · positive cases: {agg['n_positive']} · "
        f"honesty (negative) cases: {agg['n_negative']}",
        "",
        "## Headline",
        "",
        f"- **Refinement fidelity score: {agg['fidelity']:.2f}** "
        "(0.4·pin-recall + 0.4·itinerary-inclusion + 0.2·stability)",
        f"- Verified-POI pin recall: {agg['pin_recall']:.2f}",
        f"- Hard-constraint compliance (pinned & appears exactly once): {agg['inclusion_rate']:.2f}",
        f"- Pin stability across an unrelated re-refinement: {agg['stability_rate']:.2f}",
        f"- Pin precision (on-interest): {agg['pin_precision']:.2f}",
        f"- Honesty on impossible asks: {agg['honesty_rate']:.0%}",
        "",
        "## Per-case results",
        "",
        "| Case | Destination | Interest | Pin recall | Inclusion | Stability | Fidelity |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r["negative"]:
            continue
        lines.append(
            f"| {r['id']} | {r['destination']} | {r['interest']} | "
            f"{r['pin_recall']:.2f} | {r['inclusion_rate']:.2f} | "
            f"{r['stability_rate']:.2f} | {r['fidelity']:.2f} |"
        )
    lines += ["", "### Honesty cases (nothing real to pin — did we invent?)", "",
              "| Case | Destination | Interest | Honest |", "|---|---|---|---|"]
    for r in results:
        if not r["negative"]:
            continue
        verdict = "✅" if r["honest"] else f"❌ pins={r['pins']} leaked={r['leaked']}"
        lines.append(f"| {r['id']} | {r['destination']} | {r['interest']} | {verdict} |")

    if baseline_results is not None and baseline_agg is not None:
        lines += [
            "",
            "## vs ChatGPT baseline (recorded answers, same prompts, same matcher)",
            "",
            "| Metric | WanderPlanner | ChatGPT |",
            "|---|---|---|",
            f"| Verified-POI recall | {agg['pin_recall']:.2f} | {baseline_agg['verified_recall']:.2f} |",
            f"| Unverifiable suggestions | 0.00 (unverified candidates are dropped by design) "
            f"| {baseline_agg['unverifiable_rate']:.2f} |",
            f"| Honesty on impossible asks | {agg['honesty_rate']:.0%} | {baseline_agg['honesty_rate']:.0%} |",
            "",
            "WanderPlanner's pins are verified against OpenStreetMap/Wikivoyage before "
            "they can enter an itinerary; a hallucinated place is structurally unable "
            "to be pinned. The baseline column scores ChatGPT's raw suggestions against "
            "the same truth-set with the same fuzzy matcher.",
        ]

    lines.append("")
    return "\n".join(lines)
