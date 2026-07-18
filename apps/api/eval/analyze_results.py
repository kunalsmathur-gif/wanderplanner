"""Cluster and summarize failures in an eval results file.

Local equivalent of `agents-cli eval analyze` (Quality Flywheel step 4:
failure analysis) — takes a `*_results_<ts>.json` produced by
run_red_team_eval.py / run_model_comparison.py / run_wizard_eval.py and
groups the failing cases so patterns are visible without manually reading
every record.

Usage:
    python eval/analyze_results.py out/red_team_results_<ts>.json
    python eval/analyze_results.py out/model_comparison_results_<ts>.json --accuracy-threshold 0.7
    python eval/analyze_results.py out/wizard_eval_results_<ts>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from eval.config_loader import load_eval_config


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_red_team(blob: dict) -> str:
    """Groups successful attacks by category and by injection surface so a
    recurring vector (e.g. "rag_context" keeps winning) is obvious even
    with a small dataset."""
    lines = ["# Red-Team Failure Analysis (attacks that SUCCEEDED)", ""]
    details = blob.get("details", blob.get("summaries", {}))
    # run_red_team_eval.py stores per-model lists directly under a key we
    # don't have a name for in the top-level blob; details isn't populated
    # for this harness (see run_red_team_eval.py main_async), so re-derive
    # from summaries' succeeded_case_ids plus cross-reference categories if
    # present in "details" when the caller passes the raw per-model dict.
    summaries = blob.get("summaries", {})
    by_category: dict[str, list[str]] = defaultdict(list)
    by_model_category: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Prefer full per-case records if present (details), else fall back to
    # succeeded_case_ids from summaries (category unknown in that case).
    has_case_records = isinstance(details, dict) and any(isinstance(v, list) for v in details.values())
    if has_case_records:
        for model, records in details.items():
            for rec in records:
                if rec.get("attack_succeeded"):
                    cat = rec.get("category", "unknown")
                    by_category[cat].append(f"{model}:{rec.get('case_id')}")
                    by_model_category[model][cat] += 1
    else:
        for model, summary in summaries.items():
            for case_id in summary.get("succeeded_case_ids", []):
                by_category["unknown"].append(f"{model}:{case_id}")

    if not by_category:
        lines.append("No successful attacks — nothing to cluster.")
        return "\n".join(lines)

    lines.append("## By category (most-attacked first)")
    for cat, hits in sorted(by_category.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- **{cat}** ({len(hits)} successful attack(s)): {', '.join(hits)}")

    if by_model_category:
        lines.append("\n## By model")
        for model, cats in by_model_category.items():
            worst = sorted(cats.items(), key=lambda kv: -kv[1])
            lines.append(f"- {model}: " + ", ".join(f"{c}={n}" for c, n in worst))

    return "\n".join(lines)


def analyze_model_comparison(blob: dict, accuracy_threshold: float, hallucination_threshold: float, judge_threshold: float) -> str:
    """Groups per-case-per-model records by failure type: error, low
    accuracy, high hallucination rate, low judge quality — so it's clear
    whether failures cluster on one model, one case, or one metric."""
    lines = ["# Model-Comparison Failure Analysis", ""]
    details = blob.get("details", {})
    by_reason: dict[str, list[str]] = defaultdict(list)
    by_case: dict[str, list[str]] = defaultdict(list)

    for model, records in details.items():
        for rec in records:
            case_id = rec.get("case_id", "?")
            tag = f"{model}:{case_id}(run {rec.get('run', '?')})"
            if rec.get("error"):
                by_reason["error"].append(f"{tag} — {rec['error']}")
                by_case[case_id].append("error")
                continue
            accuracy = (rec.get("accuracy") or {}).get("overall")
            if accuracy is not None and accuracy < accuracy_threshold:
                by_reason["low_accuracy"].append(f"{tag} — accuracy={accuracy}")
                by_case[case_id].append("low_accuracy")
            hallucination = rec.get("hallucination_rate")
            if isinstance(hallucination, dict):
                hallucination = hallucination.get("rate")
            if hallucination is not None and hallucination > hallucination_threshold:
                by_reason["hallucination"].append(f"{tag} — rate={hallucination}")
                by_case[case_id].append("hallucination")
            judge = rec.get("judge")
            if judge and judge.get("overall", 1.0) < judge_threshold:
                by_reason["low_judge_quality"].append(f"{tag} — overall={judge.get('overall')}")
                by_case[case_id].append("low_judge_quality")

    if not by_reason:
        lines.append("No failures against the given thresholds — nothing to cluster.")
        return "\n".join(lines)

    lines.append(f"(thresholds: accuracy < {accuracy_threshold}, hallucination_rate > {hallucination_threshold}, judge_quality < {judge_threshold})\n")
    lines.append("## By failure reason")
    for reason, hits in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- **{reason}** ({len(hits)}):")
        for hit in hits:
            lines.append(f"    - {hit}")

    repeat_cases = {c: reasons for c, reasons in by_case.items() if len(reasons) > 1}
    if repeat_cases:
        lines.append("\n## Cases failing more than once (likely dataset- or prompt-specific)")
        for case_id, reasons in repeat_cases.items():
            lines.append(f"- {case_id}: {', '.join(reasons)}")

    return "\n".join(lines)


def analyze_wizard(blob: dict) -> str:
    """Groups failing invariant checks by check name and by conversation so
    a systemic regression (one check failing everywhere) is distinguishable
    from a one-off flaky turn."""
    lines = ["# Wizard Eval Failure Analysis", ""]
    by_check: dict[str, list[str]] = defaultdict(list)
    by_convo: dict[str, list[str]] = defaultdict(list)

    for convo in blob.get("results", []):
        convo_id = convo.get("id", "?")
        for idx, turn in enumerate(convo.get("turns", [])):
            for name, result in (turn.get("checks") or {}).items():
                if not result.get("passed"):
                    detail = result.get("detail", "")
                    entry = f"{convo_id} turn {idx}" + (f" — {detail}" if detail else "")
                    by_check[name].append(entry)
                    by_convo[convo_id].append(f"turn {idx}: {name}")

    if not by_check:
        lines.append("All checks passed — nothing to cluster.")
        return "\n".join(lines)

    lines.append("## By check (most-failing first)")
    for name, hits in sorted(by_check.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- **{name}** ({len(hits)} failing turn(s)):")
        for hit in hits:
            lines.append(f"    - {hit}")

    lines.append("\n## By conversation")
    for convo_id, hits in by_convo.items():
        lines.append(f"- {convo_id}: {', '.join(hits)}")

    return "\n".join(lines)


def main() -> int:
    analyze_defaults = load_eval_config().get("analyze", {})
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", type=Path, help="Path to a *_results_<ts>.json file")
    parser.add_argument("--accuracy-threshold", type=float, default=analyze_defaults.get("accuracy_threshold", 0.7))
    parser.add_argument("--hallucination-threshold", type=float, default=analyze_defaults.get("hallucination_threshold", 0.2))
    parser.add_argument("--judge-threshold", type=float, default=analyze_defaults.get("judge_threshold", 0.6))
    args = parser.parse_args()

    blob = _load(args.results)

    if "results" in blob:
        report = analyze_wizard(blob)
    elif "details" in blob and any(
        isinstance(v, list) and v and "attack_succeeded" in v[0] for v in blob["details"].values()
    ):
        report = analyze_red_team(blob)
    elif "summaries" in blob and any("attack_success_rate" in s for s in blob["summaries"].values()):
        report = analyze_red_team(blob)
    elif "details" in blob:
        report = analyze_model_comparison(
            blob, args.accuracy_threshold, args.hallucination_threshold, args.judge_threshold
        )
    else:
        print("Unrecognized results shape — expected 'results', or 'summaries'/'details' keys.", file=sys.stderr)
        return 2

    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
