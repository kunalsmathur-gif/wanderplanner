"""Per-stage wall-clock timing for the itinerary generation path.

`docs/scaling-tech-challenges.md` has listed "No observability stack" as an
open finding for months, and a 2026-07-28 check confirmed the specific gap: a
repo-wide grep for `time.time()`/`perf_counter` across `chains/` and `routers/`
returned **zero hits**. Every latency claim in the docs — the cold-start
ingestion cost, the retry cascade, the Pexels fetch — was reasoned about
statically and never measured. Meanwhile `generate_itinerary()` keeps
accumulating stages (scoring, persona injection, pin enforcement,
`generation_tier`) against a PRD budget the docs themselves call "tight".

This module is the cheapest thing that turns those arguments into numbers.

**Design notes worth reading before extending it:**

* **Stages are leaves, not nested spans.** `rag_retrieval`, `llm_api` and
  `llm_retry_sleep` are all inside what a caller would loosely call "the LLM
  step", but they are recorded separately and never as a parent too. Nested
  spans would double-count into `total_ms` and make `unaccounted_ms`
  meaningless — and `unaccounted_ms` is the field that tells you the stage list
  has a hole in it, which is the whole reason to trust the others.

* **A stage records its time even when its body raises.** The expensive cases
  are the failing ones: a Gemini call that times out after 20s costs exactly as
  much wall-clock as one that succeeds. Timing only the happy path would
  systematically under-report the latency that actually hurts, so the timer
  lives in a `finally`.

* **Sleeping is measured separately from working.** `llm_retry_sleep` exists
  because "the provider is slow" and "we chose to wait before retrying" are
  different problems with different fixes, and the retry schedule
  (5s/10s/20s/40s) can dominate a request without a single slow API call.

* **Everything degrades to a no-op when no request is being tracked.** The eval
  harness and the unit tests call `generate_itinerary()` directly, with no
  `track()` around it; instrumentation must never be the reason those break.
  Hence the `ContextVar` default of `None` and the early returns.

The `ContextVar` is safe under concurrency: FastAPI runs each request in its own
task, and `asyncio.gather`/`ensure_future` copy the context at task creation, so
child tasks see the *same* `RequestTimings` object and mutate it in place while
separate requests stay isolated. Note the corollary — `track()` must be entered
inside the task doing the work, and a child task cannot swap in a different
object for its parent.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_current_timings: ContextVar[RequestTimings | None] = ContextVar(
    "wanderplanner_request_timings", default=None
)


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


class RequestTimings:
    """Accumulates named stage durations, counters and labels for one operation."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        self._start = time.perf_counter()
        self._stages: dict[str, float] = {}
        self._counters: dict[str, int] = {}
        self._labels: dict[str, str] = {}

    def add_seconds(self, stage: str, seconds: float) -> None:
        """Accumulate, don't overwrite — a retried call enters the same stage
        several times and the total is what matters."""
        self._stages[stage] = self._stages.get(stage, 0.0) + seconds

    def increment(self, counter: str, by: int = 1) -> None:
        self._counters[counter] = self._counters.get(counter, 0) + by

    def label(self, key: str, value: str) -> None:
        self._labels[key] = value

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self._start

    def as_fields(self) -> dict[str, Any]:
        """Flat, aggregator-friendly dict: every duration in milliseconds.

        `unaccounted_ms` is deliberately included even when it is small. It is
        the self-check on this instrumentation: a large value means real time is
        being spent somewhere with no stage around it, which is exactly what you
        want to find out before drawing conclusions from the other numbers.
        """
        total = self.elapsed_seconds
        fields: dict[str, Any] = {"operation": self.operation, "total_ms": _ms(total)}
        for stage, seconds in sorted(self._stages.items()):
            fields[f"{stage}_ms"] = _ms(seconds)
        fields["unaccounted_ms"] = _ms(max(total - sum(self._stages.values()), 0.0))
        fields.update(self._counters)
        fields.update(self._labels)
        return fields


@contextmanager
def track(operation: str) -> Iterator[RequestTimings]:
    """Start tracking; every `stage()` inside this block records against it."""
    timings = RequestTimings(operation)
    token = _current_timings.set(timings)
    try:
        yield timings
    finally:
        _current_timings.reset(token)


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Time a block against the tracked operation, if any.

    Safe to wrap `await`s: this is a plain (synchronous) context manager around
    an awaiting block, so the measurement is wall-clock including any time the
    coroutine spends suspended — which is the latency the user experiences.
    """
    timings = _current_timings.get()
    if timings is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        timings.add_seconds(name, time.perf_counter() - started)


def record_seconds(stage_name: str, seconds: float) -> None:
    """Record a duration measured elsewhere (e.g. an already-known sleep)."""
    timings = _current_timings.get()
    if timings is not None:
        timings.add_seconds(stage_name, seconds)


def increment(counter: str, by: int = 1) -> None:
    timings = _current_timings.get()
    if timings is not None:
        timings.increment(counter, by)


def label(key: str, value: str) -> None:
    timings = _current_timings.get()
    if timings is not None:
        timings.label(key, value)


def current() -> RequestTimings | None:
    return _current_timings.get()


def log_timings(
    logger: logging.Logger,
    timings: RequestTimings,
    *,
    slow_threshold_seconds: float | None = None,
) -> dict[str, Any]:
    """Emit one structured record and return the fields (for tests/callers).

    Crossing `slow_threshold_seconds` logs at WARNING rather than INFO. That is
    the cheapest useful form of alerting available without an APM: a log search
    for WARNING already surfaces the slow tail, with the per-stage breakdown
    attached to say *which* stage caused it.
    """
    fields = timings.as_fields()
    is_slow = (
        slow_threshold_seconds is not None
        and fields["total_ms"] >= slow_threshold_seconds * 1000
    )
    logger.log(
        logging.WARNING if is_slow else logging.INFO,
        "%s finished in %.1fs%s",
        timings.operation,
        fields["total_ms"] / 1000,
        " (slow)" if is_slow else "",
        extra={"fields": fields},
    )
    return fields
