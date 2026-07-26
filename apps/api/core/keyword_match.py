"""Word-boundary keyword matching.

`any(kw in text for kw in KEYWORDS)` is the obvious way to ask "does this text
mention one of these words", and it is wrong whenever a keyword can appear
inside a longer word. It fails silently and in the direction that is hardest to
notice — a false *positive*, on text that looks unrelated.

Three live instances of it were found on 2026-07-26, all with user-visible
consequences:

* `core/price_extraction.py` — FOOD's "eat" matched **"great"**, so a snippet
  saying "great views" counted as food context when pricing meals.
* `chains/safety.py` — the kid-safety filter's "pub" matched **"Public Garden"**
  (also "Public Library", "Public Park"), silently deleting them from family
  itineraries; "bar" did the same to "Bara Imambara" and "Barbican".
* `core/budget_estimator.py` — the premium-tier list's "uk" matched
  **"Sukhothai"**, pricing a moderate-tier destination as premium.

This is the same failure shape as the v10.39.0 hidden-gem fix (match the token,
not the blob) — it just wasn't recognised as the same problem in these modules.

Not a general replacement for `in`: use this only where the keywords are meant
as *words*. Deliberate prefix matching (e.g. `core/budget_estimator.py`'s
"luxur", truncated on purpose to catch luxury/luxurious/luxuriously) is a
different intent and must keep using substring matching.

**Why this doesn't use `\\b` (found 2026-07-27).** Python's `\\b` is defined in
terms of `\\w`, and Devanagari *matras* (combining vowel signs such as `ा` in
`खाना`) are not word characters — `"ा".isalnum()` is `False`. So `\\bखाना\\b`
never matches, while `\\bहोटल\\b` matches fine, purely because one word happens
to end in a consonant and the other in a matra. That is a silent false
*negative*, the mirror image of the substring false positives above, and it hit
the Hindi YouTube narration corpus: 0 of 24 price-bearing chunks matched any
food or stay keyword. The boundary is therefore expressed as explicit
lookarounds over "word character **or** any Devanagari codepoint", which is
equivalent to `\\b` for ASCII text (`_` is still a word character, so
`scrapers/wikivoyage.py`'s `go_next`-style section ids still do NOT match a
bare `go` — that caveat is unchanged) and correct for Devanagari.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

# Keyword collections here are module-level constants, so this caches a handful
# of compiles rather than growing without bound.
_PATTERN_CACHE: dict[frozenset[str], re.Pattern[str]] = {}

# A "word character" for boundary purposes: Python's `\w` plus the whole
# Devanagari block, so combining marks count as part of the word rather than as
# a boundary. See the module docstring.
_WORDISH = r"[\wऀ-ॿ]"


def keyword_pattern(keywords: Iterable[str]) -> re.Pattern[str]:
    """Compiled, cached, case-insensitive word-boundary alternation.

    Multi-word keywords ("cocktail lounge", "new york") work as-is: the
    boundaries land at the outer edges of the phrase.
    """
    key = frozenset(keywords)
    pattern = _PATTERN_CACHE.get(key)
    if pattern is None:
        # Sorted for a deterministic pattern; alternation order doesn't affect
        # whether `search` finds a match.
        alternation = "|".join(re.escape(k) for k in sorted(key))
        pattern = re.compile(
            f"(?<!{_WORDISH})(?:{alternation})(?!{_WORDISH})", re.IGNORECASE
        )
        _PATTERN_CACHE[key] = pattern
    return pattern


def has_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Whether `text` contains any of `keywords` as a whole word."""
    if not text:
        return False
    return bool(keyword_pattern(keywords).search(text))
