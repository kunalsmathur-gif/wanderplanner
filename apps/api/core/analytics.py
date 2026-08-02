"""Lightweight analytics event logging, backing the admin dashboard.

Fire-and-forget by design: a failure to log an event must never break the
request it's attached to (auth, itinerary generation, external API calls).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm_usage import get_usage
from db_models import Event

_log = logging.getLogger("wanderplanner.analytics")


def _fallback(obj: Any) -> Any:
    """Last-resort encoder for values `json` refuses."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)


def _json_safe(metadata: dict | None) -> dict | None:
    """Coerce `metadata` into something the JSONB column can actually store.

    🔴 Without this a single unserialisable value silently destroys the event.
    `event_metadata` is JSONB, so the encode happens inside `db.commit()` — the
    `db.add()` above it succeeds, the failure surfaces as a `StatementError`
    from the flush, and the whole event is rolled back and lost. That is not
    hypothetical: `itinerary_generated` was passing a `DestinationInput` model
    straight through and had been failing on **every** generation in
    production, for every destination, which zeroed the admin dashboard's
    generation count while looking perfectly healthy from the request's side
    (logging is fire-and-forget, so nothing surfaced to the user).

    Coercion is deliberately lossy-but-total: a wrong-shaped value should cost
    fidelity in one field, never the entire event.
    """
    if metadata is None:
        return None
    try:
        json.dumps(metadata)
        return metadata
    except (TypeError, ValueError):
        _log.warning(
            "Analytics metadata was not JSON-serialisable; coercing. Keys: %s",
            sorted(metadata.keys()),
        )
        return json.loads(json.dumps(metadata, default=_fallback))


async def log_event(
    db: AsyncSession,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        db.add(
            Event(
                event_type=event_type,
                user_id=user_id,
                event_metadata=_json_safe(metadata),
            )
        )
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
