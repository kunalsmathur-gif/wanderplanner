"""Diff two timestamped eval results files, metric-by-metric.

Local equivalent of `agents-cli eval compare baseline.json candidate.json`
from the agents-cli eval skill. Works across all three harnesses in this
directory because they share one of two result shapes:

  - `{"summaries": {model: {metric: number, ...}}, "details": ...}`
    (run_red_team_eval.py, run_model_comparison.py)
  - `{"results": [{"id": ..., "turns": [{"checks": {name: {"passed": bool}}}]}]}`
    (run_wizard_eval.py)

Usage:
    python eval/compare_results.py out/model_comparison_results_A.json out/model_comparison_results_B.json
    python eval/compare_results.py out/wizard_eval_results_A.json out/wizard_eval_results_B.json
    python eval/compare_results.py --threshold 0.05 baseline.json candidate.json

Exit code is 1 if any regression is found (useful for CI gating), 0 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Metrics where a LOWER number is better. Everything else defaults to
# "higher is better". Unknown/non-numeric fields are shown but not judged.
LOWER_IS_BETTER = {
    "error_rate",
    "errors",
    "hallucination_rate_mean",
    "latency_ms_p50",
    "latency_ms_p95",
    "cost_usd_mean_per_request",
    "attack_success_rate",
    "attacks_succeeded",
}

# Fields to skip in the diff entirely (identifiers/lists, not metrics).
SKIP_FIELDS = {"calls", "cases", "scored", "inconclusive", "succeeded_case_ids", "by_category_success_rate", "judge_calls"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_delta(delta: float, lower_is_better: bool) -> str:
    if lower_is_better:
        arrow = "better" if delta < 0 else ("worse" if delta > 0 else "same")
    else:
        arrow = "better" if delta > 0 else ("worse" if delta < 0 else "same")
    sign = "+" if delta > 0 else ""
    return f"{sign}{round(delta, 4)} ({arrow})"


def _is_regression(delta: float, lower_is_better: bool, threshold: float) -> bool:
    if lower_is_better:
        return delta > threshold
    return delta < -threshold


def compare_summaries(baseline: dict, candidate: dict, threshold: float) -> tuple[list[str], bool]:
    """Diffs `{model: {metric: value}}` summary blocks. Returns (report_lines, has_regression)."""
    lines: list[str] = []
    has_regression = False
    models = sorted(set(baseline) | set(candidate))
    for model in models:
        lines.append(f"\n## {model}")
        b_metrics = baseline.get(model, {})
        c_metrics = candidate.get(model, {})
        if model not in baseline:
            lines.append("  (new model, not present in baseline)")
            continue
        if model not in candidate:
            lines.append("  (present in baseline, missing from candidate)")
            continue
        metrics = sorted(set(b_metrics) | set(c_metrics))
        for metric in metrics:
            if metric in SKIP_FIELDS:
                continue
            b_val, c_val = b_metrics.get(metric), c_metrics.get(metric)
            if not isinstance(b_val, (int, float)) or not isinstance(c_val, (int, float)):
                if b_val != c_val:
                    lines.append(f"  {metric}: {b_val!r} -> {c_val!r}")
                continue
            delta = c_val - b_val
            lower_is_better = metric in LOWER_IS_BETTER
            regressed = _is_regression(delta, lower_is_better, threshold)
            has_regression = has_regression or regressed
            flag = " REGRESSION" if regressed else ""
            lines.append(f"  {metric}: {b_val} -> {c_val}  delta={_fmt_delta(delta, lower_is_better)}{flag}")
    return lines, has_regression


def compare_wizard(baseline: dict, candidate: dict) -> tuple[list[str], bool]:
    """Diffs wizard-eval results by check pass-rate per check name, and flags
    conversations/turns that newly fail."""
    lines: list[str] = []
    has_regression = False

    def _check_tally(blob: dict) -> dict[str, list[bool]]:
        tally: dict[str, list[bool]] = {}
        for convo in blob.get("results", []):
            for turn in convo.get("turns", []):
                for name, result in (turn.get("checks") or {}).items():
                    tally.setdefault(name, []).append(bool(result.get("passed")))
        return tally

    b_tally, c_tally = _check_tally(baseline), _check_tally(candidate)
    for name in sorted(set(b_tally) | set(c_tally)):
        b_vals, c_vals = b_tally.get(name, []), c_tally.get(name, [])
        b_rate = round(sum(b_vals) / len(b_vals), 4) if b_vals else None
        c_rate = round(sum(c_vals) / len(c_vals), 4) if c_vals else None
        regressed = b_rate is not None and c_rate is not None and c_rate < b_rate
        has_regression = has_regression or regressed
        flag = " REGRESSION" if regressed else ""
        lines.append(f"  {name}: pass_rate {b_rate} -> {c_rate}{flag}")

    # Newly-failing (conversation_id, turn_index, check) triples.
    def _failing_set(blob: dict) -> set[tuple[str, int, str]]:
        failing = set()
        for convo in blob.get("results", []):
            for idx, turn in enumerate(convo.get("turns", [])):
                for name, result in (turn.get("checks") or {}).items():
                    if not result.get("passed"):
                        failing.add((convo.get("id", "?"), idx, name))
        return failing

    newly_failing = _failing_set(candidate) - _failing_set(baseline)
    if newly_failing:
        has_regression = True
        lines.append("\n  Newly failing (not failing in baseline):")
        for convo_id, idx, name in sorted(newly_failing):
            lines.append(f"    - {convo_id} turn {idx}: {name}")

    return lines, has_regression


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("baseline", type=Path, help="Earlier results JSON (e.g. before a prompt change)")
    parser.add_argument("candidate", type=Path, help="Later results JSON (e.g. after a prompt change)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Minimum delta magnitude to flag as a regression (default: 0.0, any regression flagged)",
    )
    args = parser.parse_args()

    baseline, candidate = _load(args.baseline), _load(args.candidate)

    print(f"Baseline:  {args.baseline}")
    print(f"Candidate: {args.candidate}")

    if "results" in baseline or "results" in candidate:
        lines, has_regression = compare_wizard(baseline, candidate)
        print("\n# Wizard eval check pass-rate diff")
    else:
        lines, has_regression = compare_summaries(
            baseline.get("summaries", {}), candidate.get("summaries", {}), args.threshold
        )
        print("\n# Per-model metric diff")

    print("\n".join(lines))

    if has_regression:
        print("\nRESULT: regression(s) detected.")
        return 1
    print("\nRESULT: no regressions detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
