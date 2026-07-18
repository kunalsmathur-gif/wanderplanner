"""Loads eval/eval_config.json — the single place to tune which metrics run
and at what thresholds, without editing runner code (agents-cli eval skill's
"externalize metrics config" guidance).

Falls back to hardcoded defaults if the file is missing/malformed so the
harnesses never hard-fail on a config problem; callers should treat this as
best-effort, not required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).parent / "eval_config.json"

_DEFAULTS: dict[str, Any] = {
    "model_comparison": {
        "default_runs": 3,
        "default_scale": [10000, 100000, 1000000],
        "metrics_to_run": ["accuracy", "hallucination_rate", "cost", "latency", "judge_quality"],
        "judge": {"enabled": True, "model": "gemini-2.5-flash"},
    },
    "red_team": {
        "metrics_to_run": ["attack_success_rate", "robustness_score", "by_category_success_rate"],
    },
    "wizard": {
        "checks_to_run": [
            "chips_is_list",
            "no_inline_json_leak",
            "chip_topic_alignment",
            "no_stale_chips_for_filled_field",
            "ready_to_generate_is_backed",
        ],
    },
    "analyze": {
        "accuracy_threshold": 0.7,
        "hallucination_threshold": 0.2,
        "judge_threshold": 0.6,
    },
}


def load_eval_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return _DEFAULTS
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"  ! eval_config.json unreadable ({e}); falling back to built-in defaults")
        return _DEFAULTS
    # Shallow-merge per top-level section so a partial config file (e.g. only
    # overriding "analyze") doesn't lose the other sections' defaults.
    merged = {**_DEFAULTS}
    for section, values in loaded.items():
        if section.startswith("_"):
            continue
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged[section] = {**merged[section], **values}
        else:
            merged[section] = values
    return merged
