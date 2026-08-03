"""Unit tests for core/tts_budget.py — the monthly character budget guard
(docs/adr/0001-anya-voice-provider.md, task tts-budget-guard).
"""
from __future__ import annotations

import pytest

import core.redis_client as redis_client_module
from core import tts_budget
from core.config import settings


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    # Force a fresh in-process cache per test so counts from other test
    # files/tests never bleed into the assertions below.
    monkeypatch.setattr(redis_client_module, "_cache", None)
    monkeypatch.setattr(settings, "redis_url", "")
    yield
    monkeypatch.setattr(redis_client_module, "_cache", None)


class TestBudgetGuard:
    async def test_starts_at_zero_chars_used(self):
        assert await tts_budget.get_chars_used_this_month() == 0

    async def test_records_and_accumulates_char_usage(self):
        await tts_budget.record_chars_used(100)
        await tts_budget.record_chars_used(50)
        assert await tts_budget.get_chars_used_this_month() == 150

    async def test_would_exceed_budget_false_under_ceiling(self, monkeypatch):
        monkeypatch.setattr(settings, "tts_monthly_char_budget", 1000)
        await tts_budget.record_chars_used(500)
        assert await tts_budget.would_exceed_budget(400) is False

    async def test_would_exceed_budget_true_over_ceiling(self, monkeypatch):
        monkeypatch.setattr(settings, "tts_monthly_char_budget", 1000)
        await tts_budget.record_chars_used(900)
        assert await tts_budget.would_exceed_budget(200) is True

    async def test_exactly_at_ceiling_does_not_exceed(self, monkeypatch):
        monkeypatch.setattr(settings, "tts_monthly_char_budget", 1000)
        await tts_budget.record_chars_used(800)
        assert await tts_budget.would_exceed_budget(200) is False
