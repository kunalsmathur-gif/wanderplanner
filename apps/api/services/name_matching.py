"""Place-name normalisation and surface-form generation.

Shared by `services/gems.py` (finding OSM POI names inside traveller comments)
and `services/poi_pinning.py` (matching LLM-proposed candidate names against
OSM POIs). Both were doing their own thing: pinning folded diacritics but
gems compared raw lowercase substrings, so the same POI could be findable by
one path and invisible to the other.

Why variants rather than fuzzy matching
---------------------------------------
Pinning compares two *names* to each other, so `SequenceMatcher` is a sensible
tool there. Gems searches for a name inside a 500-character comment, where
fuzzy ratio is meaningless — you need to know *which substrings to look for*.
This module answers that: given one OSM name, what forms would a traveller
plausibly type?

Every rule below was derived from a read-only audit of the real corpus
(2026-07-25, `youtube_comments` + `osm_pois` across 8 destinations), not from
guessing. The audit is also why the "core name" rule is deliberately timid:
stripping structural words aggressively recovered about as many false matches
as real ones.

  recovered (real)                      recovered (wrong)
  ----------------------------------    ---------------------------------
  "Matangeshwar Temple" -> matangeshwar  "Central Park"  -> central
  "Sitaramji Temple"    -> sitaramji     "Moti Park"     -> moti
  "Fort Immanuel"       -> immanuel      "The village"   -> village
  "Marine Drive, Kochi" -> marine drive

The distinctiveness guard below is the line those observations actually draw:
the true positives are single tokens of 8+ characters (or several tokens),
the false positives are shorter single tokens that double as ordinary English
words. It is a calibration against observed data, not a tuning knob to turn.

Cost: pure CPU, no LLM, no I/O.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# A name has to be at least this long to be worth searching for at all —
# below it, coincidental matches dominate.
_MIN_VARIANT_LEN = 4

# A *derived* single-token variant must clear this to be used. See the module
# docstring: 8 is where the audit's real recoveries (immanuel, sitaramji,
# matangeshwar) separate from its false ones (central, village, moti).
# Multi-token variants are exempt — two words together are distinctive enough.
_MIN_CORE_TOKEN_LEN = 8

# Words that describe *what kind of place* something is rather than which
# place it is. Peeled off the ends of a name to find the identifying core:
# a traveller writes "Matangeshwar" where OSM says "Matangeshwar Temple".
# Includes the Indic equivalents (mandir/ghat/haveli/kila) and the honorifics
# and articles that attach to them, since domestic destinations are the bulk
# of the catalogue.
_STRUCTURAL_WORDS = frozenset({
    # English
    "the", "of", "and", "a", "an",
    "temple", "church", "chapel", "cathedral", "basilica", "monastery",
    "mosque", "shrine", "synagogue", "museum", "gallery", "memorial",
    "monument", "fort", "fortress", "palace", "castle", "tower", "gate",
    "bridge", "park", "garden", "gardens", "beach", "lake", "river",
    "market", "bazaar", "bazar", "mall", "cafe", "restaurant", "hotel",
    "station", "stadium", "theatre", "theater", "cinema", "zoo", "square",
    "street", "road", "city", "town", "village", "old", "new", "grand",
    # Indic / romanised
    "mandir", "mandira", "masjid", "dargah", "gurudwara", "ghat", "ghats",
    "haveli", "mahal", "kila", "qila", "darwaza", "pol", "chowk",
    "ji", "ka", "ki", "shri", "sri", "sree", "sant", "baba",
})

# Single-word names that are pure category labels — searching for them finds
# every passing use of the common noun, never the specific place.
GENERIC_NAMES = frozenset({
    "park", "museum", "temple", "beach", "market", "cafe", "restaurant",
    "hotel", "church", "garden", "lake", "fort", "mall", "zoo", "bar",
    "castle", "tower", "bridge", "station", "harbour", "harbor", "mosque",
    "square", "palace", "gallery", "theatre", "theater", "cinema", "ghat",
    "mandir", "masjid", "village", "city",
})

# Latin letters that NFKD cannot decompose, because the mark is part of the
# letter rather than a combining accent. Folding by "decompose and drop
# combining marks" silently deletes these, which is worse than leaving them:
# Istanbul's "Kadıköy" became "kad koy" and could never match a comment
# spelling it "Kadikoy". Found 2026-07-25; the same gap was live in
# services/poi_pinning.py's own normaliser before this module absorbed it.
_UNDECOMPOSABLE_LATIN = str.maketrans({
    "ı": "i", "İ": "i", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l",
    "đ": "d", "Đ": "d", "ð": "d", "Ð": "d", "ħ": "h", "ŧ": "t",
    "ß": "ss", "þ": "th", "Þ": "th", "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
})

# Apostrophes are removed outright rather than turned into a space: people
# type "St Marys" for "St Mary's", so splitting the word leaves "mary s",
# which matches neither spelling.
_APOSTROPHES = str.maketrans({"'": "", "’": "", "ʼ": "", "`": ""})

# Latin text parenthesised inside an otherwise non-Latin name — OSM records
# "新熊野神社 (Imakumano Shrine)" and "愛染寺 (Aizen temple)" this way, and the
# Latin half is the only form an English-language comment will ever use.
_PARENTHESISED = re.compile(r"\(([^)]*)\)")
_LATIN_LETTER = re.compile(r"[A-Za-z]")

# Normalised text is [a-z0-9 ] only, so a "word boundary" is simply the
# absence of an adjacent alphanumeric. \b would also fire mid-token against
# punctuation that normalisation has already removed.
_BOUNDARY_BEFORE = r"(?<![a-z0-9])"
_BOUNDARY_AFTER = r"(?![a-z0-9])"


def normalize_name(text: str) -> str:
    """Lowercase, fold diacritics to base letters, reduce everything else to
    single spaces.

    Beyoğlu -> "beyoglu", Kadıköy -> "kadikoy", Ryōan-ji -> "ryoan ji",
    Musée d'Orsay -> "musee dorsay". Without the fold, a Turkish or French POI
    name simply cannot be found in a comment an English keyboard typed —
    live-observed: Istanbul's "Beyoğlu" had zero matches against comments that
    discussed "Beyoglu".

    Applied to comment text as well as to names, so both sides meet in the
    same alphabet.
    """
    text = text.translate(_APOSTROPHES).translate(_UNDECOMPOSABLE_LATIN)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_usable(variant: str) -> bool:
    return len(variant) >= _MIN_VARIANT_LEN and variant not in GENERIC_NAMES


def _peel(base: str) -> list[str]:
    """Progressively shorter forms of `base` with structural words removed
    from each end, keeping every intermediate form that stays distinctive.

    Intermediates are kept rather than only the fully-peeled core because the
    core is often too generic on its own: "Tilak Market Park" peels to
    "tilak market" (useful) and then to "tilak" (five letters, matches
    anything). Emitting both and letting the guard reject the second keeps
    the useful one.
    """
    out: list[str] = []
    tokens = base.split()
    while True:
        if tokens and tokens[0] in _STRUCTURAL_WORDS:
            tokens = tokens[1:]
        elif tokens and tokens[-1] in _STRUCTURAL_WORDS:
            tokens = tokens[:-1]
        else:
            break
        if not tokens:
            break
        candidate = " ".join(tokens)
        if len(tokens) == 1 and len(candidate) < _MIN_CORE_TOKEN_LEN:
            continue  # too short to be anything but a common word
        out.append(candidate)
    return out


def name_variants(name: str) -> list[str]:
    """Every surface form of `name` worth searching a comment for, most
    specific first and deduplicated.

    Ordering matters to callers that build one alternation out of several
    POIs' variants: the longest form must be offered to the regex engine
    first so "hawa mahal" wins over a bare "hawa" at the same position.
    """
    variants: list[str] = []

    def add(candidate: str) -> None:
        candidate = normalize_name(candidate)
        if candidate and _is_usable(candidate) and candidate not in variants:
            variants.append(candidate)

    add(name)

    # "Imakumano Shrine" out of "新熊野神社 (Imakumano Shrine)". Only when the
    # text outside the brackets has no Latin at all — otherwise the brackets
    # hold a disambiguator ("Victoria (Seychelles)"), not a translation, and
    # matching on it would attribute mentions of the country to the city.
    for inner in _PARENTHESISED.findall(name):
        outside = _PARENTHESISED.sub("", name)
        if _LATIN_LETTER.search(inner) and not _LATIN_LETTER.search(outside):
            add(inner)

    # "Fort Immanuel, Fort Kochi" / "Marine Drive, Kochi" — OSM routinely
    # appends the district or city after a comma, which no comment repeats.
    if "," in name:
        add(name.split(",", 1)[0])

    for base in list(variants):
        for peeled in _peel(base):
            add(peeled)

    variants.sort(key=len, reverse=True)
    return variants


def build_mention_pattern(variants: Iterable[str]) -> re.Pattern[str] | None:
    """One word-boundary-anchored alternation over a single place's variants.

    Boundaries are what stop "Ganesh" matching "Ganeshwar" and, more
    importantly, keep a short derived core from matching inside an unrelated
    longer word. Because `finditer` never returns overlapping matches and the
    alternation is ordered longest-first, a name found via several of its own
    variants ("fort immanuel" and "immanuel") yields one span, not two — so
    sentiment around it is counted once.
    """
    ordered = sorted({v for v in variants if v}, key=len, reverse=True)
    if not ordered:
        return None
    alternation = "|".join(re.escape(v) for v in ordered)
    return re.compile(f"{_BOUNDARY_BEFORE}(?:{alternation}){_BOUNDARY_AFTER}")
