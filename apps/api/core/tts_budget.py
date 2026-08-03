"""Monthly character budget guard for TTS (task tts-budget-guard,
docs/adr/0001-anya-voice-provider.md).

Deliberately conservative and simple: a single Redis (or in-process dict
fallback) counter per calendar month, checked before synthesis and
incremented after a successful call. This is not atomic against concurrent
requests on the same instance (a plain get/set, not INCRBY) — the same
stopgap tradeoff core/rate_limit.py already documents for its in-memory
limiter. Acceptable here because a hard ceiling under the free tier
(settings.tts_monthly_char_budget, default 900k vs the 1M free limit) leaves
headroom for the race window; revisit if this ever needs to be exact.
"""
from __future__ import annotations

from datetime import UTC, datetime

from core.config import settings
from core.redis_client import get_cache

_KEY_PREFIX = "tts:chars"
# Comfortably outlives a calendar month so a slow reader mid-rollover still
# sees this month's count; the key name itself (YYYY-MM) is what actually
# resets the budget each month, not the TTL.
_KEY_TTL_SECONDS = 40 * 24 * 60 * 60


def _current_month_key() -> str:
    return f"{_KEY_PREFIX}:{datetime.now(UTC).strftime('%Y-%m')}"


async def get_chars_used_this_month() -> int:
    cache = get_cache()
    value = await cache.get_json(_current_month_key())
    # `get_json` returns `object | None` by design (the cache round-trips
    # arbitrary JSON); narrow at the call site, which also treats a malformed
    # or legacy entry as "nothing spent yet" rather than raising mid-request.
    # That direction is deliberate: the counter is advisory (see the module
    # docstring's non-atomicity note) and the budget already sits 100k under
    # the free tier, so a reset counter costs headroom, not money.
    return value if isinstance(value, int) else 0


async def would_exceed_budget(additional_chars: int) -> bool:
    used = await get_chars_used_this_month()
    return (used + additional_chars) > settings.tts_monthly_char_budget


async def record_chars_used(char_count: int) -> None:
    cache = get_cache()
    key = _current_month_key()
    used = await get_chars_used_this_month()
    await cache.set_json(key, used + char_count, ttl_seconds=_KEY_TTL_SECONDS)
