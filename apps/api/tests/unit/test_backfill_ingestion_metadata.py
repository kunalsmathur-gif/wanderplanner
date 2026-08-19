"""Tests for scripts/backfill_ingestion_metadata.py — one-off backfill of
unified ingestion-metadata fields onto pre-2026-07-29 Qdrant points
(issue #61). See that script's module docstring for the recorded
backfill-vs-age-out decision and measured legacy-only shares.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from scripts.backfill_ingestion_metadata import _derive_extra_payload, _plan_backfill


def _point(point_id, payload: dict):
    p = MagicMock()
    p.id = point_id
    p.payload = payload
    return p


class TestDeriveExtraPayload:
    def test_already_migrated_point_is_skipped(self):
        payload = {"text": "hello", "language": "en", "content_type": "review"}
        assert _derive_extra_payload(payload, collection_setting="qdrant_collection_youtube_comments") == {}

    def test_derives_language_and_content_type_for_youtube_comment(self):
        payload = {"text": "great trip!", "source": "youtube_comment"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_youtube_comments")
        assert extra == {"language": "en", "content_type": "review"}

    def test_detects_hindi_via_devanagari_script(self):
        payload = {"text": "यह अच्छा है", "source": "youtube_comment"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_youtube_comments")
        assert extra["language"] == "hi"

    def test_falls_back_to_collection_default_source_when_missing(self):
        # Observed live: a handful of legacy osm_pois points have no
        # `source` key at all — must not KeyError, falls back to "osm".
        payload = {"text": "A park.", "poi_type": "park"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert extra["content_type"] == "guide"

    def test_derives_attraction_type_for_osm_from_poi_type(self):
        payload = {"text": "A museum.", "source": "osm", "poi_type": "museum"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert extra["attraction_type"] == "museum"

    def test_unmapped_poi_type_falls_back_to_activity(self):
        payload = {"text": "Something.", "source": "osm", "poi_type": "some_unmapped_type"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert extra["attraction_type"] == "activity"

    def test_missing_poi_type_omits_attraction_type_rather_than_guessing(self):
        payload = {"text": "Something.", "source": "osm"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert "attraction_type" not in extra

    def test_never_invents_country(self):
        payload = {"text": "A cafe.", "source": "osm", "poi_type": "cafe"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert "country" not in extra

    def test_never_writes_ingested_at_or_quality_score_or_source_name(self):
        # Out of this issue's scope — see module docstring for why writing
        # these during a backfill would misrepresent the point's history.
        payload = {"text": "A cafe.", "source": "osm", "poi_type": "cafe"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_osm")
        assert "ingested_at" not in extra
        assert "quality_score" not in extra
        assert "source_name" not in extra

    def test_non_osm_collection_never_gets_attraction_type(self):
        payload = {"text": "nice!", "source": "youtube_comment", "poi_type": "museum"}
        extra = _derive_extra_payload(payload, collection_setting="qdrant_collection_youtube_comments")
        assert "attraction_type" not in extra


class TestPlanBackfill:
    def test_groups_points_by_identical_computed_payload(self):
        client = MagicMock()
        client.scroll.return_value = (
            [
                _point(1, {"text": "great!", "source": "youtube_comment"}),
                _point(2, {"text": "also great!", "source": "youtube_comment"}),
                _point(3, {"text": "यह अच्छा है", "source": "youtube_comment"}),
            ],
            None,
        )

        groups = _plan_backfill(client, "youtube_comments", "qdrant_collection_youtube_comments")

        en_key = (("content_type", "review"), ("language", "en"))
        hi_key = (("content_type", "review"), ("language", "hi"))
        assert set(groups[en_key]) == {1, 2}
        assert groups[hi_key] == [3]

    def test_already_migrated_points_are_excluded_from_the_plan(self):
        client = MagicMock()
        client.scroll.return_value = (
            [
                _point(1, {"text": "old", "source": "youtube_comment"}),
                _point(2, {"text": "new", "source": "youtube_comment", "language": "en", "content_type": "review"}),
            ],
            None,
        )

        groups = _plan_backfill(client, "youtube_comments", "qdrant_collection_youtube_comments")

        all_ids = [pid for ids in groups.values() for pid in ids]
        assert all_ids == [1]

    def test_paginates_through_scroll_offsets(self):
        client = MagicMock()
        client.scroll.side_effect = [
            ([_point(1, {"text": "a", "source": "youtube_comment"})], "next-offset"),
            ([_point(2, {"text": "b", "source": "youtube_comment"})], None),
        ]

        groups = _plan_backfill(client, "youtube_comments", "qdrant_collection_youtube_comments")

        all_ids = sorted(pid for ids in groups.values() for pid in ids)
        assert all_ids == [1, 2]
        assert client.scroll.call_count == 2
