"""Deterministic (no-LLM) price extraction from free-text community snippets.

Used by `core/budget_estimator.py` to ground the stay/food components in
real per-destination data pulled from the app's existing free RAG
collections (Reddit/Wikivoyage/YouTube comments via `core/cost_grounding.py`)
when it's actually there, without reintroducing LLM guessing — which is
exactly the failure mode `core/budget_estimator.py` exists to avoid (see its
module docstring). A regex/median extraction is a blunt instrument on messy
traveller prose, so it only overrides the hand-authored default when it
finds enough plausible amounts (`min_samples`) inside a sane bound — a
single stray number is not treated as a real signal.

Two extraction passes run per snippet: an explicit currency-symbol/code
pass (`₹`/`$`/`Rs`/etc. — the original, stricter path) and a symbol-less
"bare number" pass added 2026-07-21 for casual YouTube comments that often
drop the currency symbol (e.g. "Choki dani 700 per person" rather than
"₹700 per person"). The bare-number pass is deliberately narrow — it only
fires when the number sits next to an explicit per-unit phrase ("per
person/night/day/plate", "pp") or an explicit price-reporting verb ("cost",
"paid", "spent", "charged", ...) — specifically to avoid misreading
timestamps, view/subscriber counts, phone numbers, or dates as prices.
"""
from __future__ import annotations

import re
import statistics

from core.keyword_match import has_keyword as _has_keyword

# Fixed, hand-authored FX-to-INR rates — a sanity-ballpark for converting
# foreign-currency mentions in scraped posts, not a live forex feed (same
# free-tools philosophy as the rest of this module).
_FX_TO_INR: dict[str, float] = {
    "$": 83.0, "usd": 83.0, "us$": 83.0,
    "€": 90.0, "eur": 90.0,
    "£": 105.0, "gbp": 105.0,
    "lkr": 0.28,
    "rs": 1.0, "rs.": 1.0, "inr": 1.0, "₹": 1.0,
}

_AMOUNT_RE = re.compile(
    r"(₹|\$|€|£|Rs\.?|INR|USD|LKR)\s?([\d,]+(?:\.\d+)?)\s?(k\b)?",
    re.IGNORECASE,
)

# Topic-keyword anchors (added 2026-07-21, alongside the bare-number pass
# below): a snippet retrieved for a "hotel per-night rate" query can still
# contain an unrelated in-bounds amount (e.g. a nightclub cover charge
# mentioned in the same Wikivoyage nightlife section) — live-verified this
# actually happens: a Paris "stay" grounding query pulled in "Rex Club,
# about €15" and "Pigalle, €20" (cover charges, not room rates) and
# confidently reported ₹1575/night. `extract_price_mentions_inr()`'s optional
# `context_keywords` requires an on-topic word near the amount before counting
# it. Originally that meant "anywhere in the same snippet", on the reasoning that
# chunks are short (~280 chars) and mostly single-topic; v10.40.4 narrowed it to
# per-amount sentence scoping after that assumption was shown to fail on
# multi-topic chunks (see `_amount_has_context` below).
STAY_CONTEXT_KEYWORDS = frozenset({
    "hotel", "hotels", "room", "rooms", "night", "nights", "stay", "stayed",
    "staying", "hostel", "hostels", "guesthouse", "guesthouses", "airbnb",
    "accommodation", "lodging", "riad", "resort", "resorts", "homestay",
})
FOOD_CONTEXT_KEYWORDS = frozenset({
    "meal", "meals", "food", "restaurant", "restaurants", "lunch", "dinner",
    "breakfast", "thali", "plate", "buffet", "eat", "eating", "cuisine",
    "dish", "dishes", "menu", "eatery", "eateries", "cafe", "dhaba",
    # Safe to include now that matching is word-boundary anchored: as bare
    # substrings "ate" collides with plate/private/climate and "bar" with
    # barber, which is why they were absent before.
    "ate", "bistro", "diner", "canteen", "streetfood", "snack", "snacks",
})


def _snippet_has_context(text: str, context_keywords: frozenset[str] | None) -> bool:
    """Whether `text` mentions the topic anywhere.

    Used as a cheap pre-filter and as the chunk-selection test in
    `core/cost_grounding.py`. Sound in that role and as a pre-filter: a keyword
    absent from the whole snippet cannot be present in a window inside it. It is
    *not* sufficient on its own for deciding whether a particular amount is
    on-topic — see `_amount_has_context`.

    No filter applied when `context_keywords` is None (unchanged behavior for
    any caller that doesn't opt in)."""
    if context_keywords is None:
        return True
    return _has_keyword(text, context_keywords)


# Per-amount context scoping (added 2026-07-26, replacing whole-snippet-only
# matching). The coarse test above asks "does this snippet mention food?" when
# the question is "is *this amount* a food price" — live-observed failure: a €5
# Paris bus fare was counted into the food median because the same chunk
# mentioned food elsewhere. (It was discarded by the safety floor, so the median
# was not visibly wrong — which is exactly why this needed finding rather than
# waiting to be reported.)
#
# Scoped to the amount's own sentence rather than a plain ±N window, because a
# window still admits a keyword sitting 20 chars away in a *different* sentence,
# which is the Paris case. Capped by a window as well, since a YouTube comment
# with no terminal punctuation at all is one long "sentence".
_CONTEXT_WINDOW = 90
_SENTENCE_BREAK_RE = re.compile(r"[.!?;\n]|\s-\s")


# Kinds of spending that are *not* stay or food. Not priced by this module —
# their only job is to mark a sentence as being about someone else's money, so a
# topically silent amount isn't allowed to borrow context across it.
OTHER_SPEND_KEYWORDS = frozenset({
    "bus", "metro", "subway", "train", "taxi", "tuk", "rickshaw", "uber",
    "flight", "flights", "ticket", "tickets", "fare", "fares", "transport",
    "scooter", "bike", "rental", "rent", "entry", "entrance", "admission",
    "museum", "temple", "tour", "guide", "spa", "massage", "souvenir",
    "shopping", "sim", "visa", "laundry",
})


def _window_around(text: str, start: int, end: int) -> str:
    return text[max(0, start - _CONTEXT_WINDOW): end + _CONTEXT_WINDOW]


def _sentence_around(text: str, start: int, end: int) -> str:
    """The amount's own sentence, bounded by `_CONTEXT_WINDOW` either way."""
    left = max(0, start - _CONTEXT_WINDOW)
    right = min(len(text), end + _CONTEXT_WINDOW)
    preceding = [m.end() for m in _SENTENCE_BREAK_RE.finditer(text, left, start)]
    if preceding:
        left = preceding[-1]
    following = _SENTENCE_BREAK_RE.search(text, end, right)
    if following:
        right = following.start()
    return text[left:right]


def _amount_has_context(
    text: str, start: int, end: int, context_keywords: frozenset[str] | None
) -> bool:
    """Whether the amount at `text[start:end]` is about `context_keywords`.

    Sentence-first, then widened only when the sentence says nothing about what
    was bought. Strict sentence scoping alone was measured against the live
    corpus and is *too* strict: it correctly rejects "Metro ticket €2. Dinner was
    lovely." but also rejects "We ate at a bistro. It was €25", where the amount's
    own sentence is topically silent and the food word is in the previous one.
    Real prices are phrased that way often enough that sentence-only scoping drove
    `food_per_day_estimate_inr` to None on all 8 destinations spot-checked —
    precision bought at the cost of switching the feature off.

    So: an on-topic word in the amount's own sentence accepts it; a *competing*
    kind of spending in that sentence rejects it (that is the Paris bus fare, and
    the signal is positive evidence, not absence of evidence); and only a sentence
    that names no spending at all falls back to the wider window.
    """
    if context_keywords is None:
        return True

    sentence = _sentence_around(text, start, end)
    if _has_keyword(sentence, context_keywords):
        return True

    competing = (STAY_CONTEXT_KEYWORDS | FOOD_CONTEXT_KEYWORDS | OTHER_SPEND_KEYWORDS) - context_keywords
    if _has_keyword(sentence, competing):
        return False

    return _has_keyword(_window_around(text, start, end), context_keywords)

# Bare-number amounts (no currency symbol/code) — common in casual YouTube
# comments (e.g. "Choki dani 700 per person") vs. Reddit's more explicit
# ₹/$-prefixed prose. Deliberately narrow: only matches a number when it's
# anchored to an explicit per-unit price phrase or preceded by an explicit
# price-reporting verb — NOT any bare number in the text — to avoid
# misreading timestamps ("10:30"), view/subscriber counts, phone numbers, or
# dates as prices. Assumes INR when no symbol is present (this app is
# India-first and the comments corpus is predominantly India-focused; see
# youtube_comments ingestion in scrapers/youtube_comments.py).
_NON_INR_CURRENCY_WORDS = (
    r"baht|yen|won|dirham|peso|ringgit|dong|rand|riyal|dinar|kip|taka|som|lira|"
    r"franc|krona|krone|zloty|rupiah|shekel|dollar|pound|euro"
)

_BARE_AMOUNT_UNIT_SUFFIX_RE = re.compile(
    r"\b([\d,]+(?:\.\d+)?)\s*(?:rs\.?|rupees)?\s*(?:/-)?\s*"
    r"(?:per\s+(?:person|head|pax|day|night|plate|thali)|pp\b|/\s*(?:person|head|pax|day|night|plate))"
    r"(?!\s*(?:" + _NON_INR_CURRENCY_WORDS + r"))",
    re.IGNORECASE,
)
_PRICE_VERB_PREFIX_RE = re.compile(
    r"\b(?:cost|costs|price|paid|spent|charged|budget|rate)\b"
    r"(?:\s+\w+){0,3}?\s*(?:rs\.?|rupees|inr|₹)?\s*([\d,]+(?:\.\d+)?)"
    r"(?!\s*(?:" + _NON_INR_CURRENCY_WORDS + r"))\b",
    re.IGNORECASE,
)

# Marks an amount as already expressed per full day / per night (a hotel
# nightly rate, or a "we spent ₹X per day on food" mention) rather than
# per-meal/per-dish/unspecified. Used only by the food per-day reconciliation
# (see `per_day_meal_multiplier` below) so an amount that is *already* daily
# isn't multiplied up a second time. Deliberately narrow — "per person" alone
# is ambiguous (per meal? per day?) and is treated as per-meal for food.
_DAILY_UNIT_RE = re.compile(
    r"(?:per\s+day|per\s+night|/\s*day|/\s*night|a\s+day|a\s+night|daily|pppd|"
    r"per\s+person\s+per\s+day)\b",
    re.IGNORECASE,
)


def _has_daily_unit(fragment: str) -> bool:
    return bool(_DAILY_UNIT_RE.search(fragment))


def _iter_raw_amounts(text: str):
    """Yield `(inr_amount, is_daily, start, end)` for every plausible price mention in
    `text`, across the symbol/currency-code, bare-unit-suffix, and price-verb
    passes. `is_daily` is True when the amount is explicitly a per-day/per-
    night rate; False for per-meal/per-dish/unspecified amounts (the common
    Wikivoyage "Eat"-listing case, which has no unit at all).

    Symbol-matched spans are masked with an equal-length run of spaces before
    the bare passes run, so an amount like "₹700 per person" is counted once
    (symbol pass) not twice — equal-length masking (rather than the previous
    single-space collapse) keeps every match offset aligned with `text` so
    the trailing-context unit check reads the right characters -- and lets the
    yielded `(start, end)` span index into `text` directly, which is what
    `_amount_has_context` needs to scope each amount's context."""
    masked = _AMOUNT_RE.sub(lambda m: " " * len(m.group(0)), text)

    for m in _AMOUNT_RE.finditer(text):
        symbol, raw_amount, thousands_suffix = m.group(1), m.group(2), m.group(3)
        try:
            amount = float(raw_amount.replace(",", ""))
        except ValueError:
            continue
        rate = _FX_TO_INR.get(symbol.lower().rstrip("."))
        if rate is None:
            continue
        if thousands_suffix:
            amount *= 1000
        yield amount * rate, _has_daily_unit(text[m.end():m.end() + 20]), m.start(), m.end()

    for m in _BARE_AMOUNT_UNIT_SUFFIX_RE.finditer(masked):
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        # The unit phrase is inside this match; a trailing "per day" (e.g.
        # "500 per plate per day" would be odd, but "500 pp per day" isn't)
        # is also checked.
        is_daily = _has_daily_unit(m.group(0)) or _has_daily_unit(text[m.end():m.end() + 20])
        yield amount, is_daily, m.start(), m.end()

    for m in _PRICE_VERB_PREFIX_RE.finditer(masked):
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        is_daily = _has_daily_unit(m.group(0)) or _has_daily_unit(text[m.end():m.end() + 20])
        yield amount, is_daily, m.start(), m.end()


def _first_price_offset(text: str) -> int | None:
    """Character offset of the earliest price-shaped mention in `text`, or
    None if it has none. Same three passes (and the same equal-length masking)
    as `_iter_raw_amounts`, so "contains a price" here means exactly what
    "would yield an amount" means there."""
    masked = _AMOUNT_RE.sub(lambda m: " " * len(m.group(0)), text)
    offsets = [
        m.start()
        for m in (
            _AMOUNT_RE.search(text),
            _BARE_AMOUNT_UNIT_SUFFIX_RE.search(masked),
            _PRICE_VERB_PREFIX_RE.search(masked),
        )
        if m is not None
    ]
    return min(offsets) if offsets else None


def has_price_mention(text: str) -> bool:
    """True when `text` contains at least one price-shaped mention.

    Lets callers select snippets *lexically* — by whether a price is actually
    present — instead of relying on dense-vector similarity to a price-flavoured
    query, which measures "is about the topic of cost" and demonstrably fails to
    surface short casual mentions like "Choki dani 700 per person" (they carry
    almost no topical signal for an embedding to latch onto). See
    core/cost_grounding.py::community_price_samples."""
    return _first_price_offset(text) is not None


def price_focused_excerpt(text: str, width: int = 280) -> str:
    """Excerpt of `text` centred on its first price mention.

    Retrieved chunks get truncated before extraction to bound prompt/CPU cost,
    but a blind `text[:width]` silently discards the price whenever it sits
    past `width` — the snippet then looks on-topic and contributes nothing,
    which is invisible from the outside (it just reads as "no signal found").
    Keeps ~a third of the window ahead of the amount so the trailing unit
    phrase ("per person", "/night") that qualifies it stays in view.
    Falls back to a plain head-truncation when there's no price to centre on."""
    if len(text) <= width:
        return text
    offset = _first_price_offset(text)
    if offset is None:
        return text[:width]
    start = max(0, offset - width // 3)
    return text[start:start + width]


def extract_price_mentions_inr(
    snippets: list[str],
    low_bound: float,
    high_bound: float,
    context_keywords: frozenset[str] | None = None,
    per_day_meal_multiplier: float | None = None,
) -> list[float]:
    """Extracts plausible INR amounts from free-text snippets. Amounts
    outside [low_bound, high_bound] are discarded as implausible for the
    thing being estimated (e.g. a snippet mentioning a $500,000 house
    shouldn't be read as a nightly hotel rate).

    `context_keywords` (e.g. `STAY_CONTEXT_KEYWORDS`/`FOOD_CONTEXT_KEYWORDS`),
    when given, requires an on-topic word near *each amount* — within its own
    sentence, capped at ±`_CONTEXT_WINDOW` chars — rather than merely somewhere
    in the same snippet. This guards against an in-bounds but off-topic amount (a
    club cover charge, a bus fare, a souvenir price) riding along in a snippet
    that was retrieved for overall topical similarity, or that discusses several
    kinds of spending at once. No filtering when omitted (existing callers
    unaffected).

    `per_day_meal_multiplier`, when set (food only), reconciles per-meal to
    per-day: Wikivoyage "Eat" prices are per-dish/per-meal, so a raw median
    of them is a single meal's cost, not a day's food budget. Each amount NOT
    already tagged per-day/per-night (see `_iter_raw_amounts`) is scaled by
    this factor (≈ meals/day) before the bounds check, so the bound is applied
    to the reconciled per-day figure. Amounts already expressed per-day are
    left as-is (no double-counting). Omitted (None) for stay/other callers,
    whose amounts are already per-night — behavior unchanged."""
    amounts: list[float] = []
    for text in snippets:
        if not _snippet_has_context(text, context_keywords):
            continue
        for raw, is_daily, start, end in _iter_raw_amounts(text):
            if not _amount_has_context(text, start, end, context_keywords):
                continue
            if per_day_meal_multiplier is not None and not is_daily:
                value = raw * per_day_meal_multiplier
            else:
                value = raw
            if low_bound <= value <= high_bound:
                amounts.append(value)
    return amounts


def food_per_day_estimate_inr(
    snippets: list[str],
    low_bound: float,
    high_bound: float,
    min_samples: int = 2,
    context_keywords: frozenset[str] | None = None,
    meals_per_day: float = 3.0,
) -> tuple[float | None, bool]:
    """Per-day food figure for a destination, plus whether it was *directly
    observed* as a daily rate.

    Returns `(median_inr_per_day, directly_observed)`.

    Two tiers, preferring real data over reconstruction:

    1. **Directly observed** — enough amounts already expressed per-day/per-night
       ("we spent ₹2000 a day on food"). These need no meals/day factor at all,
       so `directly_observed=True` and the result carries no uncalibrated
       assumption. This is the tier that lets the caller drop its safety floor.
    2. **Reconciled** — not enough daily mentions, so per-meal/per-dish amounts
       (the dominant Wikivoyage "Eat"-listing case) are scaled by
       `meals_per_day` and pooled with any daily ones. `directly_observed=False`:
       the result depends on an assumed meals/day and should stay floored.

    Splitting the tiers is what makes the meals/day factor progressively less
    load-bearing as ingestion improves, rather than permanently baked in: any
    destination whose corpus grows enough real daily mentions stops using it.
    Returns `(None, False)` when neither tier reaches `min_samples`."""
    daily: list[float] = []
    reconciled: list[float] = []
    for text in snippets:
        if not _snippet_has_context(text, context_keywords):
            continue
        for raw, is_daily, start, end in _iter_raw_amounts(text):
            if not _amount_has_context(text, start, end, context_keywords):
                continue
            if is_daily:
                if low_bound <= raw <= high_bound:
                    daily.append(raw)
            else:
                scaled = raw * meals_per_day
                if low_bound <= scaled <= high_bound:
                    reconciled.append(scaled)

    if len(daily) >= min_samples:
        return statistics.median(daily), True
    pooled = daily + reconciled
    if len(pooled) >= min_samples:
        return statistics.median(pooled), False
    return None, False


def median_price_inr(
    snippets: list[str],
    low_bound: float,
    high_bound: float,
    min_samples: int = 2,
    context_keywords: frozenset[str] | None = None,
    per_day_meal_multiplier: float | None = None,
) -> float | None:
    """Median of plausible price mentions found in `snippets`, or None if
    fewer than `min_samples` were found — too little signal to trust over
    the hand-authored default. `per_day_meal_multiplier` is passed straight
    through to `extract_price_mentions_inr` (food per-day reconciliation)."""
    amounts = extract_price_mentions_inr(
        snippets, low_bound, high_bound, context_keywords, per_day_meal_multiplier
    )
    if len(amounts) < min_samples:
        return None
    return statistics.median(amounts)
