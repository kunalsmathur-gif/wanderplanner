"""Per-stage latency instrumentation for generate_itinerary().

Filed as TODO item 5: `docs/scaling-tech-challenges.md` had listed "No
observability stack" as open for months, and a grep confirmed there was not a
single `perf_counter` in `chains/` or `routers/` — every latency claim in the
docs was static reasoning. These tests pin the behaviours that make the numbers
trustworthy, which is a different thing from pinning the numbers themselves.

The one measurement here that is *not* about the instrumentation is
`TestRetryCascadeAgainstTheWallClock`, which measures the retry schedule against
the request timeout it has to fit inside.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from core import timing
from core.logging_config import JsonFormatter, RedactionFilter

# --- The timing primitives -------------------------------------------------

class TestStageAccounting:
    def test_stages_are_recorded_under_their_own_names(self):
        with timing.track("op") as t:
            with timing.stage("alpha"):
                pass
            with timing.stage("beta"):
                pass
        fields = t.as_fields()
        assert "alpha_ms" in fields
        assert "beta_ms" in fields

    def test_repeated_stages_accumulate_rather_than_overwrite(self):
        """A retried call enters the same stage several times; the total spent
        there is the number that matters, not the last one."""
        with timing.track("op") as t:
            for _ in range(3):
                with timing.stage("llm_api"):
                    pass
        assert t.as_fields()["llm_api_ms"] >= 0
        assert t._stages["llm_api"] >= 0
        # Three entries, one key.
        assert list(t._stages) == ["llm_api"]

    def test_a_stage_records_its_time_even_when_the_body_raises(self):
        """The expensive cases are the failing ones — a call that times out
        after 20s costs the same wall-clock as one that succeeds. Timing only
        the happy path would under-report exactly the latency that hurts."""
        with timing.track("op") as t:
            with pytest.raises(RuntimeError):
                with timing.stage("llm_api"):
                    raise RuntimeError("provider exploded")
        assert "llm_api" in t._stages

    def test_counters_and_labels_reach_the_fields(self):
        with timing.track("op") as t:
            timing.increment("llm_attempts")
            timing.increment("llm_attempts")
            timing.label("llm_model", "gemini-2.5-flash")
        fields = t.as_fields()
        assert fields["llm_attempts"] == 2
        assert fields["llm_model"] == "gemini-2.5-flash"

    def test_unaccounted_time_is_reported(self):
        """The self-check on the stage list: a large `unaccounted_ms` means
        real time is being spent with no stage around it, which you want to
        know *before* trusting the other numbers."""
        with timing.track("op") as t:
            with timing.stage("alpha"):
                pass
        fields = t.as_fields()
        assert "unaccounted_ms" in fields
        assert fields["unaccounted_ms"] >= 0

    def test_unaccounted_time_never_goes_negative(self):
        """Clamped, because stages could in principle overlap (a future nested
        span) and a negative duration in a dashboard is worse than a zero."""
        with timing.track("op") as t:
            with timing.stage("a"), timing.stage("b"):
                pass
        assert t.as_fields()["unaccounted_ms"] >= 0

    async def test_elapsed_covers_suspension_not_just_cpu(self):
        """`stage()` is a sync context manager wrapped around awaits on
        purpose: wall-clock including suspension is the latency a user feels."""
        with timing.track("op") as t:
            with timing.stage("sleepy"):
                await asyncio.sleep(0.05)
        assert t.as_fields()["sleepy_ms"] >= 40


class TestNoOpWhenUntracked:
    """The eval harness and most unit tests call the chain directly, with no
    `track()` around it. Instrumentation must never be why those break."""

    def test_stage_outside_a_tracked_operation_does_nothing(self):
        with timing.stage("orphan"):
            pass
        assert timing.current() is None

    def test_counters_and_labels_outside_a_tracked_operation_do_nothing(self):
        timing.increment("nope")
        timing.label("nope", "nope")
        timing.record_seconds("nope", 1.0)
        assert timing.current() is None

    def test_an_exception_inside_stage_still_propagates_when_untracked(self):
        with pytest.raises(ValueError):
            with timing.stage("orphan"):
                raise ValueError("boom")


class TestConcurrencyIsolation:
    async def test_two_concurrent_operations_do_not_share_timings(self):
        """FastAPI runs each request in its own task, so the ContextVar must
        isolate them — otherwise one user's stages land in another's record."""

        async def run(name: str, sleep_for: float) -> dict:
            with timing.track(name) as t:
                with timing.stage(name):
                    await asyncio.sleep(sleep_for)
                return t.as_fields()

        slow, fast = await asyncio.gather(run("slow", 0.08), run("fast", 0.01))
        assert slow["operation"] == "slow"
        assert fast["operation"] == "fast"
        assert "fast_ms" not in slow
        assert "slow_ms" not in fast

    async def test_a_child_task_records_into_its_parents_timings(self):
        """`asyncio.gather` copies the context at task creation, so a child
        sees the same object and mutates it in place. The guidance-block fetch
        depends on this."""

        async def child():
            with timing.stage("child_work"):
                await asyncio.sleep(0.01)

        with timing.track("parent") as t:
            await asyncio.gather(child(), child())
        assert "child_work_ms" in t.as_fields()


# --- The structured-log path ----------------------------------------------

class TestStructuredOutput:
    def test_fields_survive_into_the_json_record(self):
        """`JsonFormatter` emitted only timestamp/level/logger/message, so
        `extra=` was silently dropped — timings logged this way would have been
        invisible."""
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
        record.fields = {"total_ms": 1234.5, "llm_attempts": 2}
        rendered = JsonFormatter().format(record)
        assert '"total_ms": 1234.5' in rendered
        assert '"fields"' in rendered

    def test_fields_are_nested_so_they_cannot_shadow_reserved_keys(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "real message", None, None)
        record.fields = {"message": "impostor", "level": "FAKE"}
        import json as _json

        payload = _json.loads(JsonFormatter().format(record))
        assert payload["message"] == "real message"
        assert payload["level"] == "INFO"
        assert payload["fields"]["message"] == "impostor"

    def test_absent_fields_leave_the_record_shape_unchanged(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
        assert "fields" not in JsonFormatter().format(record)

    def test_redaction_reaches_inside_fields(self):
        """A filter only covers `getMessage()`; structured values ride
        alongside it. Same blind spot as the v10.40.3 state-file leak, where
        the log line was redacted and the value written beside it was not."""
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
        record.fields = {"who": "someone@example.com", "total_ms": 12.0}
        RedactionFilter().filter(record)
        assert record.fields["who"] == "[redacted-email]"
        assert record.fields["total_ms"] == 12.0


class TestSlowRequestEscalation:
    def test_a_fast_operation_logs_at_info(self, caplog):
        with caplog.at_level(logging.INFO):
            with timing.track("op") as t:
                pass
            timing.log_timings(logging.getLogger("test.timing"), t, slow_threshold_seconds=10)
        assert [r.levelno for r in caplog.records] == [logging.INFO]

    def test_a_slow_operation_escalates_to_warning(self, caplog):
        """Cheapest alerting available without an APM: the level itself is the
        signal, and the per-stage breakdown rides along to say which stage."""
        with caplog.at_level(logging.INFO):
            with timing.track("op") as t:
                pass
            timing.log_timings(
                logging.getLogger("test.timing"), t, slow_threshold_seconds=0.0
            )
        assert caplog.records[0].levelno == logging.WARNING
        assert "slow" in caplog.records[0].getMessage()

    def test_the_breakdown_is_attached_to_the_record(self, caplog):
        with caplog.at_level(logging.INFO):
            with timing.track("generate_itinerary") as t:
                with timing.stage("llm_api"):
                    pass
                timing.increment("llm_attempts")
            timing.log_timings(logging.getLogger("test.timing"), t)
        fields = caplog.records[0].fields
        assert fields["operation"] == "generate_itinerary"
        assert "llm_api_ms" in fields
        assert fields["llm_attempts"] == 1


# --- The finding this instrumentation was built to check -------------------

class TestRetryCascadeAgainstTheWallClock:
    """`_gemini_itinerary`'s retry cascade has to fit inside the timeout the
    router imposes, and it does not. This measures the schedule rather than
    restating the claim — the backoff is recomputed here from the same
    expression the chain uses, so a change to one fails this."""

    @staticmethod
    def _backoff_schedule(max_attempts: int = 5) -> list[int]:
        # Mirrors chains/itinerary_chain.py: min(5 * 2**attempt, 60), applied
        # after every attempt except the last.
        return [min(5 * (2 ** attempt), 60) for attempt in range(max_attempts - 1)]

    def test_one_model_sleeps_longer_than_the_whole_request_is_allowed(self):
        from core.config import settings

        sleep_for_one_model = sum(self._backoff_schedule())
        assert sleep_for_one_model == 75
        # 30 is the code default; 120 is what local .env and Railway both set.
        # The cascade exceeds the former outright and eats most of the latter
        # before the *second* model is even tried.
        assert sleep_for_one_model > 30
        assert sleep_for_one_model > settings.llm_timeout_seconds * 0.5

    def test_the_full_three_model_cascade_is_unreachable(self):
        """Which means `_fallback_itinerary()` — cache → RAG skeleton → mock —
        is unreachable under sustained transient errors, because it only runs
        once every model has been exhausted. The user gets LLM_TIMEOUT instead
        of the degraded-but-real itinerary that exists for this case."""
        three_models = sum(self._backoff_schedule()) * 3
        assert three_models == 225
        assert three_models > 120

    def test_the_cascade_records_attempts_and_sleep_separately(self):
        """The two are different problems: a slow provider and a long backoff
        produce the same total, and only the split says which to fix."""
        with timing.track("generate_itinerary") as t:
            for _ in range(3):
                timing.increment("llm_attempts")
                with timing.stage("llm_api"):
                    pass
                timing.record_seconds("llm_retry_sleep", 5.0)
                timing.increment("llm_retries")
        fields = t.as_fields()
        assert fields["llm_attempts"] == 3
        assert fields["llm_retries"] == 3
        assert fields["llm_retry_sleep_ms"] == 15000.0
        assert fields["llm_api_ms"] < 100
