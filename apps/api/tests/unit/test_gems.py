"""
Unit tests for services/gems.py (hidden-gem scoring + crowd dial,
docs/GTM_STRATEGY.md §2). Qdrant scrolls are mocked — fully offline.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import services.gems as gems
from services.gems import (
    _sentiment_around,
    compute_gem_intel_sync,
    gem_prompt_block,
    get_gem_intel,
)
from services.name_matching import build_mention_pattern, name_variants, normalize_name


def _sentiment_for(text: str, name: str) -> tuple[int, int]:
    """Score `text` around every mention of `name`, going through the same
    normalise-then-match pipeline compute_gem_intel_sync uses."""
    chunk_norm = normalize_name(text)
    pattern = build_mention_pattern(name_variants(name))
    spans = [m.span() for m in pattern.finditer(chunk_norm)] if pattern else []
    return _sentiment_around(chunk_norm, spans)


def _poi(name: str, poi_type: str = "attraction", name_local: str = "") -> dict:
    return {
        "destination": "Phuket", "name": name, "poi_type": poi_type,
        "lat": 7.9, "lon": 98.3, "name_local": name_local,
    }


def _chunk(text: str, subreddit: str = "ThailandTourism") -> dict:
    return {"destination": "Phuket", "text": text, "subreddit": subreddit}


def _yt_chunk(text: str) -> dict:
    return {"destination": "Phuket", "text": text, "video_id": "abc123"}


def _mock_client(pois: list[dict], chunks: list[dict], yt_chunks: list[dict] | None = None) -> MagicMock:
    client = MagicMock()
    yt_chunks = yt_chunks or []

    def _scroll(collection_name, scroll_filter, limit, with_payload, with_vectors):
        if collection_name == "osm_pois":
            payloads = pois
        elif collection_name == "reddit":
            payloads = chunks
        elif collection_name == "youtube_comments":
            payloads = yt_chunks
        else:
            payloads = []
        points = []
        for p in payloads:
            pt = MagicMock()
            pt.payload = p
            points.append(pt)
        return points, None

    client.scroll.side_effect = _scroll
    return client


class TestSentimentAround:
    def test_positive_and_negative_counted_in_window(self):
        text = "banana beach is a stunning quiet gem, but patong is crowded and overrated"
        pos, neg = _sentiment_for(text, "Banana Beach")
        assert pos >= 3  # stunning, quiet, gem
        # patong's negativity is beyond banana beach's ±120 window? window is
        # 120 chars — the whole string fits, so negatives are counted too.
        assert neg >= 1

    def test_no_mention_returns_zero(self):
        assert _sentiment_for("nothing here", "Banana Beach") == (0, 0)

    def test_hinglish_words_counted(self):
        pos, _ = _sentiment_for("varanasi ghats are ekdum badhiya and sundar", "Varanasi Ghats")
        assert pos >= 2  # badhiya, sundar
        _, neg = _sentiment_for("chowpatty is bekar and ganda, total bakwas", "Chowpatty")
        assert neg >= 3  # bekar, ganda, bakwas

    def test_lexicon_word_touching_punctuation_is_still_counted(self):
        """Normalising the chunk before splitting means every punctuation mark
        separates tokens — the previous version hand-replaced only ",.!" so
        "gem;" or "(peaceful)" scored nothing."""
        pos, _ = _sentiment_for("banana beach: (peaceful) — a real gem; loved it", "Banana Beach")
        assert pos >= 3


class TestComputeGemIntel:
    def _run(self, pois, chunks):
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)):
            return compute_gem_intel_sync("Phuket")

    def test_low_mention_high_sentiment_is_gem(self):
        pois = [_poi("Banana Beach")]
        chunks = [
            _chunk("Banana Beach is a stunning quiet gem, absolutely loved it"),
            _chunk("if you want peaceful, Banana Beach is underrated and beautiful"),
        ]
        intel = self._run(pois, chunks)
        assert len(intel["gems"]) == 1
        gem = intel["gems"][0]
        assert gem["name"] == "Banana Beach"
        assert gem["mentions"] == 2
        assert gem["sentiment"] > 0.55
        assert "r/ThailandTourism" in gem["sources"]

    def test_high_mention_is_crowd_favourite_not_gem(self):
        pois = [_poi("Patong Beach")]
        chunks = [_chunk(f"visited Patong Beach on day {i}") for i in range(15)]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []
        assert len(intel["crowd_favourites"]) == 1
        assert intel["crowd_favourites"][0]["mentions"] == 15

    def test_zero_mentions_excluded_entirely(self):
        """No community proof → never recommend on OSM presence alone."""
        pois = [_poi("Some Unknown Cove")]
        chunks = [_chunk("talked about other places only")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []
        assert intel["crowd_favourites"] == []

    def test_negative_sentiment_excluded_from_gems(self):
        pois = [_poi("Scam Corner Market")]
        chunks = [_chunk("Scam Corner Market is overpriced, dirty and a total trap — avoid")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []

    def test_generic_single_word_names_skipped(self):
        pois = [_poi("Beach"), _poi("Park"), _poi("Zoo")]
        chunks = [_chunk("the beach and the park near the zoo are lovely and quiet")]
        intel = self._run(pois, chunks)
        assert intel["gems"] == []

    def test_empty_collections_return_empty(self):
        assert self._run([], []) == {"gems": [], "crowd_favourites": []}
        assert self._run([_poi("Banana Beach")], []) == {"gems": [], "crowd_favourites": []}

    def test_mid_range_mention_count_is_not_silently_dropped(self):
        """Regression: the old fixed thresholds (gem <= 6, crowd >= 12) left a
        dead zone — a POI mentioned 7-11 times landed in neither list and
        vanished. Live-observed for Jaipur, whose only match (Hawa Mahal,
        8 mentions) fell in the gap, so the whole feature returned empty."""
        pois = [_poi("Hawa Mahal")]
        chunks = [_chunk(f"Hawa Mahal is beautiful and worth it, visit {i}") for i in range(8)]
        intel = self._run(pois, chunks)
        assert (intel["gems"] + intel["crowd_favourites"]) != [], "8 mentions fell into the old dead zone"
        assert intel["gems"][0]["name"] == "Hawa Mahal"
        assert intel["gems"][0]["mentions"] == 8

    def test_every_mentioned_poi_is_classified_or_fails_sentiment_only(self):
        """The two branches must partition mentioned POIs: the sentiment floor
        is the only legitimate reason one appears in neither list."""
        pois = [_poi(f"Place Number {i}") for i in range(8)]
        chunks = []
        for i in range(8):
            # i+1 mentions each -> counts 1..8 spanning the old dead zone.
            chunks += [_chunk(f"Place Number {i} is lovely and quiet") for _ in range(i + 1)]
        intel = self._run(pois, chunks)
        classified = {g["name"] for g in intel["gems"]} | {c["name"] for c in intel["crowd_favourites"]}
        assert classified == {f"Place Number {i}" for i in range(8)}

    def test_crowd_threshold_is_relative_to_this_destinations_distribution(self):
        """The most-mentioned POI in a thin corpus is a crowd favourite even
        though its absolute count would have read as a 'gem' before — an
        absolute threshold can't be right for two corpus sizes at once."""
        pois = [_poi("Busy Cove")] + [_poi(f"Quiet Cove {i}") for i in range(5)]
        chunks = [_chunk(f"Busy Cove was packed, visit {i}") for i in range(7)]
        for i in range(5):
            chunks.append(_chunk(f"Quiet Cove {i} is a stunning quiet gem"))
        intel = self._run(pois, chunks)
        assert [c["name"] for c in intel["crowd_favourites"]] == ["Busy Cove"]
        assert {g["name"] for g in intel["gems"]} == {f"Quiet Cove {i}" for i in range(5)}

    def test_thin_corpus_falls_back_to_absolute_threshold(self):
        """Below _MIN_POIS_FOR_RELATIVE_SPLIT a percentile is meaningless — a
        lone 5-mention POI must stay a gem, not become 'the crowd'."""
        pois = [_poi("Solo Cove")]
        chunks = [_chunk(f"Solo Cove is a stunning quiet gem, trip {i}") for i in range(5)]
        intel = self._run(pois, chunks)
        assert [g["name"] for g in intel["gems"]] == ["Solo Cove"]
        assert intel["crowd_favourites"] == []

    def test_relative_threshold_never_exceeds_absolute_ceiling(self):
        """A well-covered destination must not push the bar so high that
        genuinely famous places get recommended as hidden gems."""
        pois = [_poi("Famous Palace")] + [_poi(f"Mega Site {i}") for i in range(5)]
        chunks = [_chunk(f"Famous Palace is lovely, day {i}") for i in range(14)]
        for i in range(5):
            chunks += [_chunk(f"Mega Site {i} is lovely, day {j}") for j in range(40)]
        intel = self._run(pois, chunks)
        crowd_names = {c["name"] for c in intel["crowd_favourites"]}
        assert "Famous Palace" in crowd_names  # 14 mentions >= absolute ceiling of 12
        assert intel["gems"] == []

    def test_fewer_mentions_rank_higher_at_equal_sentiment(self):
        pois = [_poi("Quiet Cove"), _poi("Known Cove")]
        chunks = (
            [_chunk("Quiet Cove is a stunning quiet gem")]
            + [_chunk(f"Known Cove is a stunning quiet gem, visit {i}") for i in range(4)]
        )
        intel = self._run(pois, chunks)
        names = [g["name"] for g in intel["gems"]]
        assert names.index("Quiet Cove") < names.index("Known Cove")

    def test_youtube_source_blended_with_reddit(self):
        """docs/NEXT_SESSION_TODO.md item 3 — YouTube comments should
        contribute mentions/sentiment alongside Reddit, with "YouTube"
        provenance distinct from a subreddit label."""
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        yt_chunks = [_yt_chunk("Banana Beach was so peaceful and gorgeous, loved it")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks, yt_chunks)):
            intel = compute_gem_intel_sync("Phuket")
        assert len(intel["gems"]) == 1
        gem = intel["gems"][0]
        assert gem["mentions"] == 2
        assert "r/ThailandTourism" in gem["sources"]
        assert "YouTube" in gem["sources"]

    def test_youtube_only_source_still_works_without_reddit(self):
        pois = [_poi("Banana Beach")]
        yt_chunks = [_yt_chunk("Banana Beach is underrated and beautiful, a real gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, [], yt_chunks)):
            intel = compute_gem_intel_sync("Phuket")
        assert len(intel["gems"]) == 1
        assert intel["gems"][0]["sources"] == ["YouTube"]


class TestNameMatching:
    """Regressions for the 2026-07-25 live audit: raw lowercase substring
    matching found almost nothing, so destinations with hundreds of real
    comments still returned empty gem lists."""

    def _run(self, pois, chunks, destination="Phuket"):
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)):
            return compute_gem_intel_sync(destination)

    def test_diacritics_in_poi_name_match_ascii_comments(self):
        """Istanbul live: 'Beyoğlu' scored zero against a comment about
        climbing 'that Beyoglu hill'."""
        pois = [_poi("Beyoğlu Meydanı")]
        chunks = [_chunk("beyoglu meydani is a lovely quiet spot", "travel")]
        intel = self._run(pois, chunks, "Istanbul")
        assert [g["name"] for g in intel["gems"]] == ["Beyoğlu Meydanı"]

    def test_structural_suffix_stripped_to_find_mention(self):
        """Khajuraho live: 'Matangeshwar Temple' vs a comment saying
        'Matangeshwar Mahadev wala temple'."""
        pois = [_poi("Matangeshwar Temple")]
        chunks = [_chunk("boht amazing, specially Matangeshwar Mahadev wala temple", "IndiaTravel")]
        intel = self._run(pois, chunks, "Khajuraho")
        assert [g["name"] for g in intel["gems"]] == ["Matangeshwar Temple"]

    def test_comma_appended_locality_dropped(self):
        """Kochi live: OSM's 'Marine Drive, Kochi' vs comments saying just
        'Marine Drive'."""
        pois = [_poi("Marine Drive, Kochi")]
        chunks = [_chunk("Marine Drive is beautiful, loved the walk", "Kerala")]
        intel = self._run(pois, chunks, "Kochi")
        assert [g["name"] for g in intel["gems"]] == ["Marine Drive, Kochi"]

    def test_local_name_matched_when_english_name_is_a_translation(self):
        """Post-v10.39.0 OSM payloads keep both names. Where `name:en` is a
        translation rather than a transliteration, the local form is a
        genuinely different string travellers still use."""
        pois = [_poi("Army Museum", name_local="Musée de l'Armée")]
        chunks = [_chunk("musee de l'armee is a beautiful, quiet find", "Paris")]
        intel = self._run(pois, chunks, "Paris")
        assert [g["name"] for g in intel["gems"]] == ["Army Museum"]

    def test_non_latin_local_name_contributes_nothing_rather_than_crashing(self):
        """A Latin-only matcher cannot search Japanese text; the POI must
        still rank on its English name."""
        pois = [_poi("Kiyomizu-dera", name_local="清水寺")]
        chunks = [_chunk("kiyomizu-dera was serene and beautiful", "JapanTravel")]
        intel = self._run(pois, chunks, "Kyoto")
        assert [g["name"] for g in intel["gems"]] == ["Kiyomizu-dera"]

    def test_common_word_core_does_not_manufacture_mentions(self):
        """Audit false positives: 'Central Park' must not match a bare
        'central', nor 'Moti Park' a bare 'moti'."""
        pois = [_poi("Central Park"), _poi("Moti Park")]
        chunks = [_chunk("the central station is near moti bazaar, both lovely")]
        intel = self._run(pois, chunks, "Delhi")
        assert intel["gems"] == []
        assert intel["crowd_favourites"] == []

    def test_mention_requires_word_boundary(self):
        pois = [_poi("Ganesh Temple")]
        chunks = [_chunk("we went to ganeshwar, it was lovely and quiet")]
        intel = self._run(pois, chunks, "Khajuraho")
        assert intel["gems"] == []


class TestNonGemPoiTypes:
    def _run(self, pois, chunks, destination="Phuket"):
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)):
            return compute_gem_intel_sync(destination)

    def test_train_stations_are_never_gems(self):
        """Istanbul live: the entire gem list was Kadıköy, Karaköy and
        Beyoğlu — three metro stops."""
        pois = [_poi("Kadıköy", poi_type="train station")]
        chunks = [_chunk("kadikoy is a beautiful, calm, underrated area", "travel")]
        intel = self._run(pois, chunks, "Istanbul")
        assert intel["gems"] == []

    def test_train_stations_are_not_crowd_favourites_either(self):
        """'De-prioritise the train station' is not advice."""
        pois = [_poi("Railway Station", poi_type="train station")]
        chunks = [_chunk(f"rent a scooter from the Railway Station, trip {i}") for i in range(15)]
        intel = self._run(pois, chunks, "Jaipur")
        assert intel["crowd_favourites"] == []

    def test_visitable_types_still_rank(self):
        pois = [_poi("Banana Beach", poi_type="beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        intel = self._run(pois, chunks)
        assert [g["name"] for g in intel["gems"]] == ["Banana Beach"]

    def test_poi_named_after_the_destination_is_excluded(self):
        """Khajuraho live: the strongest 'gem' was a POI called 'Khajuraho',
        which matched every comment that named the town."""
        pois = [_poi("Khajuraho"), _poi("Chaunsath Yogini Temple")]
        chunks = [
            _chunk("khajuraho is beautiful and worth it"),
            _chunk("chaunsath yogini temple is a peaceful gem"),
        ]
        intel = self._run(pois, chunks, "Khajuraho")
        names = {g["name"] for g in intel["gems"]} | {c["name"] for c in intel["crowd_favourites"]}
        assert names == {"Chaunsath Yogini Temple"}


class TestGemPromptBlock:
    _INTEL = {
        "gems": [{
            "name": "Banana Beach", "poi_type": "beach", "lat": 7.9, "lon": 98.3,
            "mentions": 3, "sentiment": 0.9, "sources": ["r/ThailandTourism"],
            "gem_score": 0.4,
        }],
        "crowd_favourites": [{
            "name": "Patong Beach", "poi_type": "beach", "lat": 7.9, "lon": 98.3,
            "mentions": 40, "sentiment": 0.5, "sources": [], "gem_score": 0.09,
        }],
    }

    def test_touristy_returns_empty(self):
        assert gem_prompt_block(self._INTEL, "touristy") == ""

    def test_empty_gems_returns_empty(self):
        assert gem_prompt_block({"gems": [], "crowd_favourites": []}, "offbeat") == ""

    def test_balanced_lists_gems_without_crowd_section(self):
        block = gem_prompt_block(self._INTEL, "balanced")
        assert "Banana Beach" in block
        assert "3 traveller post(s)" in block
        assert "r/ThailandTourism" in block
        assert "90% positive" in block
        assert "CROWD-HEAVY" not in block

    def test_offbeat_includes_crowd_heavy_deprioritisation(self):
        block = gem_prompt_block(self._INTEL, "offbeat")
        assert "Banana Beach" in block
        assert "CROWD-HEAVY" in block
        assert "Patong Beach" in block


@pytest.mark.asyncio
class TestGetGemIntelCache:
    async def test_second_call_served_from_cache(self):
        gems._cache.clear()
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)) as mock_get:
            first = await get_gem_intel("Phuket")
            second = await get_gem_intel("Phuket")
        assert first == second
        assert mock_get.call_count == 1  # compute ran once; second call was a cache hit

    async def test_expired_cache_recomputes(self):
        gems._cache.clear()
        pois = [_poi("Banana Beach")]
        chunks = [_chunk("Banana Beach is a stunning quiet gem")]
        with patch("services.gems.get_qdrant", return_value=_mock_client(pois, chunks)) as mock_get:
            await get_gem_intel("Phuket")
            # age the entry past TTL
            ts, intel = gems._cache["Phuket"]
            gems._cache["Phuket"] = (ts - gems._CACHE_TTL_SECONDS - 1, intel)
            await get_gem_intel("Phuket")
        assert mock_get.call_count == 2
