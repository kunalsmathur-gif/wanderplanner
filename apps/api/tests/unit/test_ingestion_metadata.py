"""Unit tests for core/ingestion_metadata.py (issue #33, docs/rag-strategy.md §11).

Fully offline — the module is pure functions over dicts, no network or Qdrant.
"""
from __future__ import annotations

import pytest

from core.ingestion_metadata import (
    OSM_POI_TYPE_TO_ATTRACTION,
    SOURCE_CONTENT_TYPE,
    build_ingestion_payload,
    detect_language,
)


class TestLegacyFieldsPreserved:
    """The four fields every scraper and reader already used must survive
    byte-identical — ~40k live points and every consumer depend on them."""

    def test_legacy_four_fields_unchanged(self):
        p = build_ingestion_payload(
            destination="Jaipur", source="wikivoyage", text="Hawa Mahal is free.",
            source_url="https://en.wikivoyage.org/wiki/Jaipur",
        )
        assert p["destination"] == "Jaipur"
        assert p["source"] == "wikivoyage"
        assert p["text"] == "Hawa Mahal is free."
        assert p["source_url"] == "https://en.wikivoyage.org/wiki/Jaipur"

    def test_quality_score_default_matches_search_fallback(self):
        """services/search.py:492 does .get("quality_score", 0.5). If this
        default drifted, newly-ingested docs would silently rank differently
        from legacy ones that have no field at all."""
        p = build_ingestion_payload(destination="Goa", source="reddit", text="x")
        assert p["quality_score"] == 0.5

    def test_extra_fields_merged(self):
        p = build_ingestion_payload(
            destination="Kyoto", source="youtube_comment", text="x",
            extra={"video_id": "abc123", "like_count": 7},
        )
        assert p["video_id"] == "abc123"
        assert p["like_count"] == 7

    def test_published_date_omitted_when_empty(self):
        """Absent rather than empty-string: Qdrant filters on a field that
        exists, so writing "" would make every undated doc match a
        date-present filter."""
        assert "published_date" not in build_ingestion_payload(
            destination="Goa", source="reddit", text="x"
        )
        assert build_ingestion_payload(
            destination="Goa", source="reddit", text="x", published_date="2026-03-15"
        )["published_date"] == "2026-03-15"


class TestContentType:
    @pytest.mark.parametrize(("source", "expected"), [
        ("wikivoyage", "guide"),
        ("wikivoyage_itinerary", "itinerary"),
        ("osm", "guide"),
        ("reddit", "review"),
        ("youtube_comment", "review"),
        ("youtube_transcript", "vlog_transcript"),
        ("youtube_description", "vlog_transcript"),
    ])
    def test_source_maps_to_content_type(self, source, expected):
        p = build_ingestion_payload(destination="X", source=source, text="t")
        assert p["content_type"] == expected

    def test_every_source_string_the_scrapers_write_is_mapped(self):
        """Guards the one way this map rots: a new scraper (or a renamed
        `source`) silently falling through to the "guide" default."""
        written_by_scrapers = {
            "wikivoyage", "osm", "reddit",
            "youtube_comment", "youtube_transcript", "youtube_description",
        }
        assert written_by_scrapers <= set(SOURCE_CONTENT_TYPE)

    def test_unknown_source_falls_back_rather_than_raising(self):
        p = build_ingestion_payload(destination="X", source="brand_new", text="t")
        assert p["content_type"] == "guide"


class TestLanguageDetection:
    def test_plain_english(self):
        assert detect_language("The fort opens at 9am and costs 200 rupees.") == "en"

    def test_devanagari(self):
        assert detect_language("हवा महल का टिकट ₹200 का है।") == "hi"

    def test_hinglish_mixed_script_is_hindi_not_english(self):
        """Presence, not ratio — a ratio threshold files mixed chunks as
        English and hides exactly the domestic content v10.41.0 added."""
        assert detect_language("Jaipur ka khana ₹200 me मिल जाता है") == "hi"

    def test_rupee_sign_alone_is_not_devanagari(self):
        """₹ is U+20B9 (Currency Symbols), outside the U+0900-U+097F block.
        An English chunk quoting a rupee price must stay "en"."""
        assert detect_language("Dinner for two costs ₹1,500 here.") == "en"

    @pytest.mark.parametrize("value", ["", None])
    def test_empty_and_none_default_to_english(self, value):
        assert detect_language(value) == "en"


class TestAttractionType:
    @pytest.mark.parametrize(("poi_type", "expected"), [
        ("restaurant", "restaurant"),
        ("cafe", "restaurant"),
        ("museum", "museum"),
        ("beach", "nature"),
        ("park", "nature"),
        ("train station", "transport"),
        ("airport", "transport"),
        ("historic monument", "landmark"),
        ("place of worship", "landmark"),
    ])
    def test_osm_poi_type_maps(self, poi_type, expected):
        assert OSM_POI_TYPE_TO_ATTRACTION[poi_type] == expected

    def test_unmapped_poi_type_is_not_in_the_map(self):
        """`_poi_type()` returns this literal when no tag matches; osm.py
        supplies "activity" via .get()'s default, so it must stay absent here
        rather than being mapped to something more specific."""
        assert "place of interest" not in OSM_POI_TYPE_TO_ATTRACTION

    def test_every_mapped_poi_type_exists_in_the_osm_query_table(self):
        """OSM_POI_TYPE_TO_ATTRACTION keys are the human-readable labels from
        scrapers/osm.py::POI_TAG_QUERIES. A typo here is invisible — it just
        silently never matches — so pin the two together."""
        from scrapers.osm import POI_TAG_QUERIES

        real_labels = set(POI_TAG_QUERIES.values())
        unknown = set(OSM_POI_TYPE_TO_ATTRACTION) - real_labels
        assert not unknown, f"mapped poi_types that osm.py never emits: {unknown}"

    def test_attraction_type_absent_when_not_supplied(self):
        p = build_ingestion_payload(destination="X", source="reddit", text="t")
        assert "attraction_type" not in p
