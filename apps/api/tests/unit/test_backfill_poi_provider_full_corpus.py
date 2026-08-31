"""Tests for scripts/backfill_poi_provider_full_corpus.py's state-file
helpers — the resumability contract this one-off full-corpus backfill
depends on (see module docstring: a killed/interrupted run must not have to
re-spend Google Places quota/cost on already-completed destinations)."""
from __future__ import annotations

import json

from scripts.backfill_poi_provider_full_corpus import _append_state, _load_completed


class TestStateFileRoundtrip:
    def test_load_completed_returns_empty_dict_when_file_missing(self, tmp_path, monkeypatch):
        missing_path = tmp_path / "does_not_exist.jsonl"
        monkeypatch.setattr(
            "scripts.backfill_poi_provider_full_corpus.STATE_PATH", str(missing_path),
        )
        assert _load_completed() == {}

    def test_append_then_load_roundtrips_rows_keyed_by_destination(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.jsonl"
        monkeypatch.setattr(
            "scripts.backfill_poi_provider_full_corpus.STATE_PATH", str(state_path),
        )

        _append_state({"destination": "Jaipur", "poi_count": 72, "provider_used": "google_places"})
        _append_state({"destination": "Goa", "poi_count": 0, "provider_used": None, "error": "timeout"})

        completed = _load_completed()

        assert set(completed) == {"Jaipur", "Goa"}
        assert completed["Jaipur"]["poi_count"] == 72
        assert completed["Goa"]["error"] == "timeout"

    def test_append_state_writes_one_json_line_per_call(self, tmp_path, monkeypatch):
        state_path = tmp_path / "state.jsonl"
        monkeypatch.setattr(
            "scripts.backfill_poi_provider_full_corpus.STATE_PATH", str(state_path),
        )

        _append_state({"destination": "Lisbon", "poi_count": 40})
        _append_state({"destination": "Porto", "poi_count": 35})

        lines = state_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["destination"] == "Lisbon"
        assert json.loads(lines[1])["destination"] == "Porto"

    def test_a_later_call_overwrites_an_earlier_destination_on_load(self, tmp_path, monkeypatch):
        # _append_state is append-only, but _load_completed keys by
        # destination, so a re-run's later row for the same destination
        # wins when building the resume set -- this is what makes --force
        # re-runs safe to combine with resumability.
        state_path = tmp_path / "state.jsonl"
        monkeypatch.setattr(
            "scripts.backfill_poi_provider_full_corpus.STATE_PATH", str(state_path),
        )

        _append_state({"destination": "Bali", "poi_count": 0, "error": "quota exceeded"})
        _append_state({"destination": "Bali", "poi_count": 58, "error": None})

        completed = _load_completed()
        assert completed["Bali"]["poi_count"] == 58
        assert completed["Bali"]["error"] is None
