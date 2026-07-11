"""Lightweight analytics event logging, backing the admin dashboard.

Fire-and-forget by design: a failure to log an event must never break the
request it's attached to (auth, itinerary generation, external API calls).
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db_models import Event
from core.llm_usage import get_usage

_log = logging.getLogger("wanderplanner.analytics")


async def log_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        db.add(Event(event_type=event_type, user_id=user_id, event_metadata=metadata))
        await db.commit()
    except Exception:
        _log.exception("Failed to log analytics event %s", event_type)
        await db.rollback()


async def flush_llm_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
) -> None:
    """Persist whatever external-API usage was recorded (via
    core/llm_usage.py) during the current request. Covers both Gemini calls
    (token counts + estimated USD cost) and lighter-weight calls like Pexels
    (call-count only, for free-tier rate-limit awareness). Call once per
    request, after the chain/service calls complete — safe no-op if nothing
    was recorded (e.g. the mock/RAG-fallback path ran instead of a real
    Gemini call).
    """
    calls = get_usage()
    if not calls:
        return

    gemini_calls = [c for c in calls if c.get("provider") == "gemini"]
    other_calls = [c for c in calls if c.get("provider") != "gemini"]
    total_tokens = sum(c.get("total_tokens", 0) for c in gemini_calls)
    total_cost_usd = round(sum(c.get("cost_usd", 0.0) for c in gemini_calls), 6)

    if gemini_calls:
        await log_event(
            db,
            "gemini_usage",
            user_id=user_id,
            metadata={
                "calls": gemini_calls,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost_usd,
            },
        )

    # Group non-Gemini calls (e.g. Pexels) by provider for a simple call-count
    # event per provider — these are free-tier APIs where we mainly care
    # about approaching rate limits, not token/cost accounting.
    by_provider: dict[str, list[dict]] = {}
    for c in other_calls:
        by_provider.setdefault(c.get("provider", "unknown"), []).append(c)
    for provider, provider_calls in by_provider.items():
        await log_event(
            db,
            f"{provider}_usage",
            user_id=user_id,
            metadata={"calls": provider_calls, "call_count": len(provider_calls)},
        )
