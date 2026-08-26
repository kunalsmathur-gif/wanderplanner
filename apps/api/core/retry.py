"""Generic exponential-backoff retry helper for scheduled ingestion jobs.

Used inside the 2-4AM IST off-peak window (core/scheduler.py) so a
transient failure (network blip, momentary Qdrant/API hiccup) gets a few
same-night retries instead of silently waiting for the job's next full
cadence (e.g. another 7 days for the itinerary corpus) — while staying
comfortably inside the 2-hour window rather than risking a retry storm
into peak hours.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    job_name: str,
    max_attempts: int = 4,
    base_delay_seconds: float = 300.0,
    max_total_delay_seconds: float | None = 3600.0,
) -> T:
    """Call `fn()`, retrying with exponential backoff (base_delay_seconds *
    2**attempt) on any exception, up to `max_attempts` total tries.

    Re-raises the final exception if every attempt fails — callers decide
    whether that means "log and wait for the next scheduled window" (the
    pattern every caller in core/scheduler.py uses) or something else.

    `max_total_delay_seconds` is a safety cap (default 1 hour) on the sum of
    all sleep time, so a large `max_attempts`/`base_delay_seconds`
    combination can never itself run past the 2-4AM off-peak window into
    peak hours — attempts stop early (raising the last error) if the next
    backoff sleep would exceed the remaining budget.
    """
    delay = base_delay_seconds
    total_slept = 0.0
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt == max_attempts:
                break
            if max_total_delay_seconds is not None and total_slept + delay > max_total_delay_seconds:
                logger.warning(
                    "%s: attempt %d/%d failed (%s), but next backoff delay would exceed the "
                    "%.0fs retry budget — giving up early rather than risk running into peak hours",
                    job_name, attempt, max_attempts, e, max_total_delay_seconds,
                )
                break
            logger.warning(
                "%s: attempt %d/%d failed (%s) — retrying in %.0fs",
                job_name, attempt, max_attempts, e, delay,
            )
            await asyncio.sleep(delay)
            total_slept += delay
            delay *= 2

    assert last_error is not None  # max_attempts >= 1 guarantees at least one failure recorded here
    logger.error("%s: all %d attempt(s) failed, giving up until the next scheduled run", job_name, max_attempts)
    raise last_error
