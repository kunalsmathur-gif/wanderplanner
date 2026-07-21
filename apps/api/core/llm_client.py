"""Helper to extract token-usage + estimated cost from google-genai SDK
responses and feed them into the per-request usage accumulator
(core/llm_usage.py), which routers then persist as analytics `events` for
the admin cost dashboard.

Pricing is intentionally approximate (public list pricing per 1M tokens,
USD) — it exists to give the admin dashboard a directional cost signal, not
to reconcile against actual Google Cloud billing.
"""
from __future__ import annotations

import logging
from typing import Any

from core.llm_usage import record_usage

logger = logging.getLogger("wanderplanner.llm_cost")

# (input_$_per_1M_tokens, output_$_per_1M_tokens) — approximate public pricing.
# Non-Gemini entries added for eval/run_model_comparison.py (docs/eval-set.md
# §8, model-selection eval) — same "directional signal, not a billing
# reconciliation" caveat applies; re-verify against each provider's current
# published rate card before treating a comparison as final.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite-preview-06-17": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "llama-3.1-70b-versatile": (0.59, 0.79),      # Groq
    "llama-3.3-70b-versatile": (0.59, 0.79),      # Groq
    "gpt-4o": (2.50, 10.00),                       # OpenAI
    "gpt-4o-mini": (0.15, 0.60),                   # OpenAI
    "claude-3-5-sonnet-20241022": (3.00, 15.00),   # Anthropic
    "claude-3-5-haiku-20241022": (0.80, 4.00),     # Anthropic
    "kimi-k2-0711-preview": (0.60, 2.50),           # Moonshot (published rate card, eval/run_budget_comparison.py, docs/eval-set.md §14)
    "moonshot-v1-8k": (0.20, 1.00),                 # Moonshot
}
_DEFAULT_PRICING = (0.10, 0.40)


def estimate_cost_usd(model: str, prompt_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price


def track_gemini_usage(response: Any, *, model: str, purpose: str) -> None:
    """Extract usage_metadata from a google-genai `generate_content` response
    and record it in the current request's usage accumulator. Safe no-op if
    usage_metadata is absent (e.g. an older SDK version or a mocked response
    in tests) — cost tracking must never break the actual generation call.
    """
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        total_tokens = getattr(usage, "total_token_count", None) or (prompt_tokens + output_tokens)
        record_usage(
            provider="gemini",
            model=model,
            purpose=purpose,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=round(estimate_cost_usd(model, prompt_tokens, output_tokens), 6),
        )
    except Exception:
        logger.exception("Failed to record Gemini usage for purpose=%s model=%s", purpose, model)
