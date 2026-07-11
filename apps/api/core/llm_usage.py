"""Per-request accumulator for LLM token-usage records.

Uses a ContextVar so concurrent requests (each with their own asyncio task)
don't clobber each other's usage lists. Routers bracket a request with
reset_usage()/get_usage() around the chain call; chain code calls
record_usage() whenever it gets a Gemini usage_metadata payload back.

Safe no-op if called outside a bracketed context (e.g. background jobs) —
record_usage() just does nothing rather than raising.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

_usage_ctx: ContextVar[Optional[list]] = ContextVar("_usage_ctx", default=None)


def reset_usage() -> None:
    """Start (or restart) collecting usage records for the current task."""
    _usage_ctx.set([])


def record_usage(**kwargs: Any) -> None:
    bucket = _usage_ctx.get()
    if bucket is None:
        return
    bucket.append(kwargs)


def get_usage() -> list:
    bucket = _usage_ctx.get()
    return bucket if bucket is not None else []
