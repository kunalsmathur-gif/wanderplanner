"""Multi-turn wizard eval runner (docs/eval-set.md Section 1 automated
equivalent).

Replays each scripted conversation in eval/wizard_dataset.json against the
REAL chains.wizard_chat_chain.wizard_chat() entrypoint -- one live Gemini
call per turn, exactly like the production /api/wizard-chat endpoint --
merging each turn's config_patch into partial_config the same way the
frontend does (apps/web/components/wizard/LLMWizard.tsx's one-level-deep
object merge) before sending the next turn.

Every turn's (reply, chips, config_patch, ready_to_generate) is checked
against eval/wizard_checks.py's deterministic invariants. This is a
state-machine correctness eval -- it does NOT judge conversational quality
(see eval/run_model_comparison.py's LLM-judge metric for that), it catches
structural bugs like the 2026-07-18 production incident where a
budget-confirmation reply carried pace chips underneath it.

COSTS REAL MONEY -- one live Gemini call per turn across all conversations
(small: current dataset is ~10 turns total, gemini-2.0-flash pricing).
Requires GEMINI_API_KEY + llm_provider != "mock" in apps/api/.env.

Usage (from apps/api, venv python):
    python -m eval.run_wizard_eval
    python -m eval.run_wizard_eval --yes
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from chains.wizard_chat_chain import WizardChatRequest, wizard_chat
from core.config import settings
from eval.config_loader import load_eval_config
from eval.wizard_checks import run_all_checks
from models.chat import ChatMessage

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET_PATH = Path(__file__).parent / "wizard_dataset.json"
OUT_DIR = Path(__file__).parent / "out"


def load_dataset() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _merge_config_patch(base: dict, patch: dict) -> dict:
    """One-level-deep merge, mirroring LLMWizard.tsx's frontend merge logic
    exactly -- nested dict fields (budget, group, dates, destination) get
    shallow-merged; everything else is replaced outright. Using a different
    merge strategy here than production would silently test the wrong
    thing."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        existing = merged.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            merged[key] = {**existing, **value}
        else:
            merged[key] = value
    return merged


async def run_conversation(convo: dict, checks_to_run: list[str] | None = None) -> dict:
    config = copy.deepcopy(convo.get("seed_partial_config") or {})
    messages: list[ChatMessage] = []
    turn_records = []

    for user_text in convo["turns"]:
        messages.append(ChatMessage(role="user", content=user_text))
        request = WizardChatRequest(messages=messages, partial_config=config)
        response = await wizard_chat(request)

        config_after = _merge_config_patch(config, response.config_patch or {})
        record = {
            "user_text": user_text,
            "reply": response.reply,
            "chips": response.chips,
            "config_patch": response.config_patch,
            "config_before": config,
            "config_after": config_after,
            "ready_to_generate": response.ready_to_generate,
        }
        record["checks"] = run_all_checks(record, checks_to_run)
        turn_records.append(record)

        messages.append(ChatMessage(role="assistant", content=response.reply, config_patch=response.config_patch or {}))
        config = config_after

    return {"id": convo["id"], "note": convo.get("note", ""), "turns": turn_records}


def _turn_passed(turn: dict) -> bool:
    return all(c["passed"] for c in turn["checks"].values())


def render_report(results: list[dict]) -> str:
    lines = ["# WanderPlanner — Wizard Multi-Turn Eval Report", ""]
    total_turns = sum(len(r["turns"]) for r in results)
    failed_turns = sum(1 for r in results for t in r["turns"] if not _turn_passed(t))
    lines.append(f"**{total_turns - failed_turns}/{total_turns} turns passed all checks** "
                 f"across {len(results)} conversation(s).\n")

    for convo in results:
        convo_ok = all(_turn_passed(t) for t in convo["turns"])
        status = "✅" if convo_ok else "❌"
        lines.append(f"## {status} `{convo['id']}`")
        if convo["note"]:
            lines.append(f"_{convo['note']}_\n")
        for i, turn in enumerate(convo["turns"], start=1):
            turn_ok = _turn_passed(turn)
            t_status = "✅" if turn_ok else "❌"
            lines.append(f"- {t_status} Turn {i} — user: \"{turn['user_text']}\"")
            lines.append(f"  - reply: {turn['reply'][:160]!r}")
            lines.append(f"  - chips: {turn['chips']}")
            if not turn_ok:
                for check_name, result in turn["checks"].items():
                    if not result["passed"]:
                        lines.append(f"  - ⚠️ FAILED `{check_name}`: {result['detail']}")
        lines.append("")
    return "\n".join(lines)


async def main_async() -> None:
    dataset = load_dataset()
    checks_to_run = load_eval_config().get("wizard", {}).get("checks_to_run")
    results = []
    for convo in dataset["conversations"]:
        print(f"  > running conversation '{convo['id']}' ({len(convo['turns'])} turns)...")
        result = await run_conversation(convo, checks_to_run)
        results.append(result)
        for i, turn in enumerate(result["turns"], start=1):
            status = "✅" if _turn_passed(turn) else "❌"
            print(f"      {status} turn {i}: chips={turn['chips']}")

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_path = OUT_DIR / f"wizard_eval_results_{ts}.json"
    report_path = OUT_DIR / f"wizard_eval_report_{ts}.md"
    results_path.write_text(json.dumps({"results": results}, indent=2, default=str), encoding="utf-8")
    report = render_report(results)
    report_path.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Full results: {results_path}")
    print(f"Report:       {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="Skip the cost-estimate confirmation prompt")
    args = parser.parse_args()

    dataset = load_dataset()
    num_turns = sum(len(c["turns"]) for c in dataset["conversations"])

    if settings.llm_provider == "mock" or not settings.gemini_api_key:
        print("llm_provider is 'mock' or GEMINI_API_KEY is unset — wizard_chat() will use the "
              "scripted mock path, not real Gemini. This eval is only meaningful against the "
              "live model; set GEMINI_API_KEY and llm_provider!=mock in apps/api/.env first.")
        return

    print(f"This will make {num_turns} live Gemini calls ({settings.gemini_model}) across "
          f"{len(dataset['conversations'])} conversation(s).")
    if not args.yes:
        confirm = input("Proceed? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
