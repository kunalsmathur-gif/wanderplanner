#!/usr/bin/env bash
# Two-phase runner for eval/run_model_comparison.py (docs/eval-set.md §8).
#
# Phase 1 (smoke test): the 4 models that previously failed most/all calls
# under the shared 8192-token cap (gpt-5-mini, gpt-5-nano, claude-sonnet-5,
# gpt-5.6-terra) — now raised to 16384 via MAX_TOKENS_OVERRIDES in
# eval/llm_providers.py — run with --runs 1 first. If any of them still
# error out on every case, STOP: re-running the full battery won't fix
# that model, it'll just burn more OpenRouter credit on the same failure.
#
# Phase 2 (full run): all 15 models discussed, --runs 3 (config default),
# 6 cases, judge enabled. Only runs if you confirm after reviewing phase 1.
#
# Usage (from apps/api):
#   bash eval/run_full_model_comparison.sh
#   SKIP_SMOKE_TEST=1 bash eval/run_full_model_comparison.sh   # go straight to phase 2
#
# Requires: OPENROUTER_API_KEY set (in .env or exported), venv active or
# .venv/bin/python present, and OpenRouter account credit topped up BEFORE
# running (a $0-balance run previously produced a full set of invalid,
# still-billed data — see docs/eval-set.md §8D).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."  # -> apps/api

PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo "!! $PYTHON not found/executable. Set PYTHON=... or activate your venv first." >&2
  exit 1
fi

if [ -z "${OPENROUTER_API_KEY:-}" ] && ! grep -q '^OPENROUTER_API_KEY=' .env 2>/dev/null; then
  echo "!! OPENROUTER_API_KEY not set (checked env and .env). All openrouter/* models will be skipped." >&2
  read -r -p "Continue anyway? [y/N] " reply
  [ "$reply" = "y" ] || exit 1
fi

TS="$(date -u +%Y%m%d_%H%M%S)"
LOG_DIR="eval/out/run_logs"
mkdir -p "$LOG_DIR"

# Previously-broken models needing the raised max_tokens override to be
# verified live before spending on the full battery.
SMOKE_MODELS="openrouter/openai/gpt-5-mini,openrouter/openai/gpt-5-nano,openrouter/anthropic/claude-sonnet-5,openrouter/openai/gpt-5.6-terra"

# Full 15-model set discussed: 12 base OpenRouter models + gpt-5.6-luna +
# the 2 smoke-tested frontier models (gpt-5-mini/gpt-5-nano already
# included above, not duplicated).
FULL_MODELS="openrouter/google/gemini-2.5-flash,openrouter/google/gemini-3.5-flash-lite,openrouter/google/gemini-2.5-flash-lite,openrouter/anthropic/claude-haiku-4.5,openrouter/openai/gpt-4o-mini,openrouter/openai/gpt-5-mini,openrouter/openai/gpt-5-nano,openrouter/openai/gpt-5.6-luna,openrouter/meta-llama/llama-3.3-70b-instruct,openrouter/meta-llama/llama-3.1-8b-instruct,openrouter/moonshotai/kimi-k2,openrouter/deepseek/deepseek-chat,openrouter/deepseek/deepseek-v4-flash,openrouter/anthropic/claude-sonnet-5,openrouter/openai/gpt-5.6-terra"

if [ "${SKIP_SMOKE_TEST:-0}" != "1" ]; then
  echo "=== Phase 1: smoke test (--runs 1) on previously-broken models ==="
  echo "Models: $SMOKE_MODELS"
  SMOKE_LOG="$LOG_DIR/smoke_${TS}.log"
  "$PYTHON" -m eval.run_model_comparison --models "$SMOKE_MODELS" --runs 1 --yes 2>&1 | tee "$SMOKE_LOG"

  echo
  echo "=== Phase 1 done. Review $SMOKE_LOG (and eval/out/model_comparison_report.md) above. ==="
  echo "Look for 'Error Rate' > 0 or missing rows for gpt-5-mini / gpt-5-nano / claude-sonnet-5 / gpt-5.6-terra."
  read -r -p "All 4 models produced usable (non-zero-row, low-error) results? Proceed to the full 15-model / --runs 3 battery? [y/N] " proceed
  if [ "$proceed" != "y" ]; then
    echo "Stopping after phase 1. Fix the failing model(s) (or drop them from FULL_MODELS below) before re-running."
    exit 0
  fi
else
  echo "SKIP_SMOKE_TEST=1 set — skipping phase 1, going straight to the full run."
fi

echo
echo "=== Phase 2: full run — 15 models, --runs 3, 6 cases, judge enabled ==="
echo "Models: $FULL_MODELS"
echo "Estimated cost: ~\$6-9 (see chat history / docs/eval-set.md §8 for the breakdown)."
FULL_LOG="$LOG_DIR/full_${TS}.log"
"$PYTHON" -m eval.run_model_comparison --models "$FULL_MODELS" --runs 3 --yes 2>&1 | tee "$FULL_LOG"

echo
echo "=== Done ==="
echo "Report:  eval/out/model_comparison_report.md (latest alias)"
echo "Results: eval/out/model_comparison_results.json (latest alias)"
echo "Logs:    $FULL_LOG"
echo
echo "To diff against the previous run:"
echo "  $PYTHON eval/compare_results.py eval/out/model_comparison_results_20260820_043357.json eval/out/model_comparison_results_<new_ts>.json"
