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
"""
from __future__ import annotations

import re
from collections.abc import Iterable

# Keyword collections here are module-level constants, so this caches a handful
# of compiles rather than growing without bound.
_PATTERN_CACHE: dict[frozenset[str], re.Pattern[str]] = {}


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
        pattern = re.compile(r"\b(?:" + alternation + r")\b", re.IGNORECASE)
        _PATTERN_CACHE[key] = pattern
    return pattern


def has_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Whether `text` contains any of `keywords` as a whole word."""
    if not text:
        return False
    return bool(keyword_pattern(keywords).search(text))
