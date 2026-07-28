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

The distinctiveness guard: length was the wrong question
--------------------------------------------------------
The first version of that guard was a length threshold — a derived single
token had to be 8+ characters, which is where the recoveries above separate
from the false ones. It was calibrated, but on the wrong variable, and
`name_variants("Egyptian Museum")` is the counter-example that shows it:
peeling "museum" leaves the bare token **egyptian**, which is 8 characters and
sails through. Live-measured 2026-07-27, Cairo's Egyptian Museum carried **30
mentions, 29 of them from that token** — "egyptian food", "as an egyptian".
The real name appeared in one chunk.

The threshold cannot be raised out of the problem: `egyptian` is exactly 8
characters and so is `immanuel`, the genuine recovery above. Length was
standing in for the question that actually matters — **is this token an
ordinary English word, or is it specific to this place?** — so the guard now
asks that directly, against a word list generated from the embedding model's
own WordPiece vocabulary (see `scripts/generate_common_words.py`; a token that
survives in a 30k frequency-built vocabulary *as a whole word* is by
construction a common word). Length is kept as a cheap first gate, so both
rules apply.

Measured across the full corpus (9,892 POIs, all 168 destinations, 2026-07-28):
of 521 distinct derived single-token cores, **144 are common words** and are
now rejected. They fall into exactly two groups, both of which were matching
things that are not the POI:

  * ordinary words — `national` (20 POIs), `botanical`, `government`,
    `parliament`, `auditorium`, `traditional`, `military`, `university`
  * demonyms and place names at the *wrong scale* — `egyptian`, `japanese`,
    `himalayan`, and city/district names like `melbourne`, `singapore`,
    `edinburgh`, `kensington`, whose every mention is about the city, not
    about "Melbourne Museum"

⚠️ **The known cost, stated rather than hidden: fame and vocabulary membership
correlate.** `guggenheim`, `griffith` and `hollywood` are real identities that
travellers do use bare, and they are in the vocabulary *because* they are
famous, so they are rejected too. For the gems consumer that is close to
harmless — a POI famous enough to be a BERT token is not a hidden gem — but it
is a genuine recall loss and the reason to reach for a curated exception list
here, if one is ever needed, rather than for a lower threshold.

The asymmetry that justifies being conservative: a wrong variant **corrupts**
the output (mentions attributed to a place nobody named), while a missing
variant merely falls back to matching the full name, which is what happened
before peeling existed at all.

Cost: pure CPU, no LLM, no network. The word list is read from disk once and
cached; the runtime path never loads the embedding model.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

# A name has to be at least this long to be worth searching for at all —
# below it, coincidental matches dominate.
_MIN_VARIANT_LEN = 4

# A *derived* single-token variant must clear this to be used. See the module
# docstring: 8 is where the audit's real recoveries (immanuel, sitaramji,
# matangeshwar) separate from its false ones (central, village, moti).
# Multi-token variants are exempt — two words together are distinctive enough.
# This is now the cheap *first* gate; `_is_common_word` is the one that
# actually answers "is this a name or a word".
_MIN_CORE_TOKEN_LEN = 8

# Generated, not hand-written — `scripts/generate_common_words.py` regenerates
# it from the embedding model's vocabulary. Exported so that script and the
# tests read the same two values rather than re-deciding them.
COMMON_WORDS_PATH = Path(__file__).resolve().parent / "data" / "common_english_words.txt"
MIN_COMMON_WORD_LEN = _MIN_CORE_TOKEN_LEN

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


@lru_cache(maxsize=1)
def _common_words() -> frozenset[str]:
    """The generated word list, read once per process.

    A missing file is deliberately fatal rather than silently permissive: the
    quiet failure mode would be every demonym becoming a search term again,
    which reads as a working feature returning inflated mention counts — the
    exact bug this guard exists to prevent.
    """
    return frozenset(COMMON_WORDS_PATH.read_text(encoding="utf-8").split())


def _is_common_word(token: str) -> bool:
    """Whether `token` is an ordinary English word rather than a place-specific
    name. See the module docstring for what "ordinary" means here and how the
    list is built."""
    return token in _common_words()


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

    Both single-token guards apply here and nowhere else — a name a mapper
    actually gave a place is used as-is, however generic it reads; only a form
    *we* derived has to earn its place.
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
        if len(tokens) == 1:
            if len(candidate) < _MIN_CORE_TOKEN_LEN:
                continue  # too short to be anything but a common word
            if _is_common_word(candidate):
                continue  # "Egyptian Museum" -> "egyptian" matches egyptian food
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
