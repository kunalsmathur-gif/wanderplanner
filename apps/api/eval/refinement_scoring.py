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

CAVEATS — read before treating a high score as "the pipeline is doing well"
(found and documented 2026-07-20, see docs/eval-set.md §4V and
docs/NEXT_SESSION_TODO.md's POI-pinning section for the full incident):

1. "Honest"/"verified" measure EXISTENCE, not RELEVANCE or DATA COMPLETENESS.
   A pin can be fully honest (a real place, real coordinates, genuinely in
   the OSM/wiki data) while still being a poor match for the stated named
   interest — verification's OSM path still has no thematic-relevance check,
   it only checks "is this a real, findable place." Live-reproduced
   2026-07-20: RF-001 (London/Harry Potter, expected_pois =
   ["Warner Bros. Studio Tour London", "Leadenhall Market", "Platform 9 3/4"])
   pinned "Borough Market" via the wiki fallback — a real, wiki-documented
   London place with no real Harry Potter connection. This exact defect was
   already flagged once in the 2026-07-13 live run's known-defects list and
   only partially addressed (a candidate-proposal-side prompt tweak).
   **Fixed 2026-07-20** for the wiki-fallback path specifically:
   `services/poi_pinning.py::verify_candidates_sync` now requires the
   wiki chunk that matches the candidate's name to also mention a keyword
   from the named interest before it counts as verified (see
   `_interest_keywords`/regression tests in `test_interest_pinning.py`) —
   Borough Market no longer survives an unrelated Harry Potter refinement.
   The OSM path is unaffected by this fix (OSM matches are name-exact
   against curated map nodes, a narrower risk surface) and still carries
   no thematic check; existence-vs-relevance remains a live distinction
   worth remembering when reading a high score.

2. These pure functions score against whatever data they're handed — they
   say nothing about whether that data (real OSM/wiki collections in
   production) is actually good. Offline mode's fixtures are hand-curated
   and self-contained by design (fast, free, deterministic regression gate),
   so a perfect offline score has never implied the production ingestion
   pipeline was healthy. It wasn't, for months (see the v10.27.0 writeup):
   `scrapers/osm.py` was producing 100%-food/drink POI pools and
   `scrapers/wikivoyage.py` was silently returning zero chunks for every
   destination, invisible to this module because it never touches real
   Qdrant collections. A live rerun (`--live`) exercises real data and would
   surface this class of bug, but wasn't run again between 2026-07-15 and
   this fix landing — a recommended follow-up is a small, separate
   data-completeness pre-flight check against real collections (non-zero
   wiki chunks, minimum OSM POI count, no single OSM category dominating),
   tracked as its own gate rather than folded into fidelity/honesty.
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
    """Errored cases (runner failures, e.g. persistent LLM 503s) carry an
    "error" key: excluded from every mean but counted — a fidelity claim must
    never quietly average over cases that didn't run."""
    scored = [r for r in results if "error" not in r]
    positives = [r for r in scored if not r["negative"]]
    negatives = [r for r in scored if r["negative"]]
    return {
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "n_errored": sum(1 for r in results if "error" in r),
        "expansion_recall": _mean(positives, "expansion_recall"),
        "pin_recall": _mean(positives, "pin_recall"),
        "pin_precision": _mean(positives, "pin_precision"),
        "inclusion_rate": _mean(positives, "inclusion_rate"),
        "stability_rate": _mean(positives, "stability_rate"),
        "fidelity": _mean(positives, "fidelity"),
        "honesty_rate": (
            sum(1 for r in negatives if r.get("honest")) / len(negatives) if negatives else 1.0
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
    baseline_label: str = "ChatGPT",
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
    ]
    if agg.get("n_errored"):
        lines += [
            "",
            f"⚠️ **{agg['n_errored']} case(s) errored and are excluded from every "
            "aggregate above — rerun before publishing these numbers.**",
        ]
    lines += [
        "",
        "## Per-case results",
        "",
        "| Case | Destination | Interest | Pin recall | Inclusion | Stability | Fidelity |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r["negative"]:
            continue
        if "error" in r:
            lines.append(
                f"| {r['id']} | {r['destination']} | {r['interest']} | "
                f"⚠️ errored: {r['error']} | | | |"
            )
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
        if "error" in r:
            verdict = f"⚠️ errored: {r['error']}"
        elif r["honest"]:
            verdict = "✅"
        else:
            verdict = f"❌ pins={r['pins']} leaked={r['leaked']}"
        lines.append(f"| {r['id']} | {r['destination']} | {r['interest']} | {verdict} |")

    if baseline_results is not None and baseline_agg is not None:
        lines += [
            "",
            f"## vs {baseline_label} baseline (recorded answers, same prompts, same matcher)",
            "",
            f"| Metric | WanderPlanner | {baseline_label} |",
            "|---|---|---|",
            f"| Verified-POI recall | {agg['pin_recall']:.2f} | {baseline_agg['verified_recall']:.2f} |",
            f"| Unverifiable suggestions | 0.00 (unverified candidates are dropped by design) "
            f"| {baseline_agg['unverifiable_rate']:.2f} |",
            f"| Honesty on impossible asks | {agg['honesty_rate']:.0%} | {baseline_agg['honesty_rate']:.0%} |",
            "",
            "WanderPlanner's pins are verified against OpenStreetMap/Wikivoyage before "
            "they can enter an itinerary; a hallucinated place is structurally unable "
            f"to be pinned. The baseline column scores {baseline_label}'s raw suggestions "
            "against the same truth-set with the same fuzzy matcher.",
        ]

    lines.append("")
    return "\n".join(lines)
