"""Tests for core/retry.py's `with_backoff` exponential-backoff helper."""

from __future__ import annotations

import pytest

from core.retry import with_backoff


class _CountingFailer:
    """Callable that fails `fail_times` times then succeeds, recording delays
    passed to the patched `asyncio.sleep`."""

    def __init__(self, fail_times: int, exc: type[Exception] = RuntimeError):
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    async def __call__(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc(f"boom {self.calls}")
        return "ok"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Never actually sleep in tests; just record the requested delays."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("core.retry.asyncio.sleep", _fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_succeeds_on_first_try_without_sleeping(_no_real_sleep):
    fn = _CountingFailer(fail_times=0)

    result = await with_backoff(fn, job_name="test-job")

    assert result == "ok"
    assert fn.calls == 1
    assert _no_real_sleep == []


@pytest.mark.asyncio
async def test_succeeds_after_retries_with_exponential_delays(_no_real_sleep):
    fn = _CountingFailer(fail_times=2)

    result = await with_backoff(
        fn, job_name="test-job", max_attempts=4, base_delay_seconds=1.0
    )

    assert result == "ok"
    assert fn.calls == 3
    # Two failures before success => two sleeps, doubling each time.
    assert _no_real_sleep == [1.0, 2.0]


@pytest.mark.asyncio
async def test_raises_last_error_after_exhausting_max_attempts(_no_real_sleep):
    fn = _CountingFailer(fail_times=10, exc=ValueError)

    with pytest.raises(ValueError, match="boom 3"):
        await with_backoff(fn, job_name="test-job", max_attempts=3, base_delay_seconds=1.0)

    assert fn.calls == 3
    # Sleeps happen only between attempts, not after the final failed one.
    assert _no_real_sleep == [1.0, 2.0]


@pytest.mark.asyncio
async def test_gives_up_early_when_next_delay_would_exceed_budget(_no_real_sleep):
    fn = _CountingFailer(fail_times=10, exc=RuntimeError)

    with pytest.raises(RuntimeError, match="boom 2"):
        await with_backoff(
            fn,
            job_name="test-job",
            max_attempts=10,
            base_delay_seconds=3.0,
            max_total_delay_seconds=5.0,
        )

    # attempt 1 fails -> would sleep 3s (3 <= 5 budget) -> sleeps, total_slept=3
    # attempt 2 fails -> next delay would be 6s, 3+6=9 > 5 budget -> gives up early
    assert fn.calls == 2
    assert _no_real_sleep == [3.0]


@pytest.mark.asyncio
async def test_max_total_delay_seconds_none_disables_budget_cap(_no_real_sleep):
    fn = _CountingFailer(fail_times=3)

    result = await with_backoff(
        fn,
        job_name="test-job",
        max_attempts=5,
        base_delay_seconds=1000.0,
        max_total_delay_seconds=None,
    )

    assert result == "ok"
    assert fn.calls == 4
    assert _no_real_sleep == [1000.0, 2000.0, 4000.0]
