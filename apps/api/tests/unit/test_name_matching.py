"""
Unit tests for services/name_matching.py.

The cases here are not invented: each one is a name that appeared in the
2026-07-25 read-only audit of the live `osm_pois` corpus, paired with the
form real traveller comments actually used. The false-positive tests matter
as much as the recovery tests — the audit's first cut of this logic recovered
roughly as many wrong matches as right ones.
"""
from __future__ import annotations

from services.name_matching import (
    build_mention_pattern,
    name_variants,
    normalize_name,
)


def _matches(name: str, text: str) -> bool:
    """Would `name` be counted as mentioned in `text`?"""
    pattern = build_mention_pattern(name_variants(name))
    return bool(pattern and pattern.search(normalize_name(text)))


class TestNormalizeName:
    def test_folds_diacritics(self):
        assert normalize_name("Beyoğlu") == "beyoglu"
        assert normalize_name("Kadıköy") == "kadikoy"
        assert normalize_name("Musée Grévin") == "musee grevin"
        assert normalize_name("Ryōan-ji") == "ryoan ji"

    def test_folds_letters_nfkd_cannot_decompose(self):
        """The mark is part of the letter, so "decompose and drop combining
        marks" deletes it entirely instead of folding it."""
        assert normalize_name("Kadıköy") == "kadikoy"
        assert normalize_name("Nørrebro") == "norrebro"
        assert normalize_name("Łazienki") == "lazienki"

    def test_strips_punctuation_and_collapses_whitespace(self):
        assert normalize_name("Warner Bros.  Studio Tour!") == "warner bros studio tour"

    def test_apostrophes_are_removed_not_split(self):
        """People type "St Marys"; splitting on the apostrophe gives
        "mary s", which matches neither spelling."""
        assert normalize_name("St Mary's Convent") == "st marys convent"

    def test_non_latin_script_normalizes_to_empty(self):
        """Japanese/Devanagari names carry no matchable Latin text — callers
        rely on this to skip them rather than crash."""
        assert normalize_name("清水寺") == ""
        assert normalize_name("जंतर मंतर") == ""


class TestNameVariants:
    def test_longest_form_first(self):
        variants = name_variants("Matangeshwar Temple")
        assert variants[0] == "matangeshwar temple"

    def test_strips_trailing_structural_word(self):
        """Live: 'Matangeshwar Temple' was mentioned as 'Matangeshwar Mahadev
        wala temple' in a Khajuraho comment and matched nothing."""
        assert "matangeshwar" in name_variants("Matangeshwar Temple")

    def test_strips_leading_structural_word(self):
        assert "immanuel" in name_variants("Fort Immanuel")

    def test_drops_comma_appended_locality(self):
        """OSM appends the district or city; comments never repeat it."""
        assert "marine drive" in name_variants("Marine Drive, Kochi")

    def test_extracts_latin_from_parentheses_of_local_script_name(self):
        assert "imakumano shrine" in name_variants("新熊野神社 (Imakumano Shrine)")

    def test_parenthetical_disambiguator_is_not_treated_as_translation(self):
        """'Victoria (Seychelles)' brackets a country, not a translation —
        matching on it would credit mentions of the country to the city."""
        assert "seychelles" not in name_variants("Victoria (Seychelles)")

    def test_keeps_useful_intermediate_when_full_core_is_too_generic(self):
        """'Tilak Market Park' peels to 'tilak market' (specific) and then to
        'tilak' (five letters, matches anything) — keep the first, drop the
        second."""
        variants = name_variants("Tilak Market Park")
        assert "tilak market" in variants
        assert "tilak" not in variants

    def test_generic_single_word_names_yield_nothing(self):
        assert name_variants("Park") == []
        assert name_variants("Temple") == []
        assert name_variants("Mosque") == []

    def test_non_latin_name_yields_nothing(self):
        assert name_variants("清水寺") == []


class TestDistinctivenessGuard:
    """The core-name rule must not manufacture matches out of common words.
    Every case below is a false positive observed live during the audit."""

    def test_central_park_does_not_match_bare_central(self):
        assert not _matches("Central Park", "the central station area is nice")

    def test_moti_park_does_not_match_bare_moti(self):
        assert not _matches("Moti Park", "we stayed near moti bazaar")

    def test_the_village_does_not_match_bare_village(self):
        assert not _matches("The village", "a lovely fishing village nearby")

    def test_short_core_of_famous_name_is_not_used(self):
        """'Hawa Mahal' must match as a whole; 'hawa' alone would match
        'hawa hawai' and any other passing use."""
        assert "hawa" not in name_variants("Hawa Mahal")


class TestMentionPattern:
    def test_matches_diacritic_name_in_ascii_comment(self):
        """Live: Istanbul's 'Beyoğlu' scored zero against a comment that
        explicitly discussed climbing 'that Beyoglu hill'."""
        assert _matches("Beyoğlu", "I climbed that Beyoglu hill a thousand times")

    def test_respects_word_boundaries(self):
        assert _matches("Ganesh Temple", "the ganesh temple was calm")
        assert not _matches("Ganesh Temple", "we visited ganeshwar instead")

    def test_matches_are_case_and_punctuation_insensitive(self):
        assert _matches("St Mary's Convent", "loved ST. MARYS CONVENT")

    def test_empty_variants_give_no_pattern(self):
        assert build_mention_pattern([]) is None

    def test_overlapping_variants_of_one_name_yield_a_single_span(self):
        """'fort immanuel' and 'immanuel' both match here; sentiment must be
        counted once, so finditer has to return one span, not two."""
        pattern = build_mention_pattern(name_variants("Fort Immanuel"))
        assert len(pattern.findall(normalize_name("Fort Immanuel is lovely"))) == 1
