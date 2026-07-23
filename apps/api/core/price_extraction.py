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
# confidently reported ₹1575/night. `extract_price_mentions_inr()`'s
# optional `context_keywords` requires at least one on-topic word to appear
# *anywhere in the same snippet* as the amount before counting it — coarser
# than per-amount proximity, but the snippet chunks here are short (~280
# chars) and single-topic enough that this is a real signal, not just noise.
STAY_CONTEXT_KEYWORDS = frozenset({
    "hotel", "hotels", "room", "rooms", "night", "nights", "stay", "stayed",
    "staying", "hostel", "hostels", "guesthouse", "guesthouses", "airbnb",
    "accommodation", "lodging", "riad", "resort", "resorts", "homestay",
})
FOOD_CONTEXT_KEYWORDS = frozenset({
    "meal", "meals", "food", "restaurant", "restaurants", "lunch", "dinner",
    "breakfast", "thali", "plate", "buffet", "eat", "eating", "cuisine",
    "dish", "dishes", "menu", "eatery", "eateries", "cafe", "dhaba",
})


def _snippet_has_context(text: str, context_keywords: frozenset[str] | None) -> bool:
    """No filter applied when `context_keywords` is None (unchanged behavior
    for any caller that doesn't opt in)."""
    if context_keywords is None:
        return True
    lowered = text.lower()
    return any(keyword in lowered for keyword in context_keywords)

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
    """Yield `(inr_amount, is_daily)` for every plausible price mention in
    `text`, across the symbol/currency-code, bare-unit-suffix, and price-verb
    passes. `is_daily` is True when the amount is explicitly a per-day/per-
    night rate; False for per-meal/per-dish/unspecified amounts (the common
    Wikivoyage "Eat"-listing case, which has no unit at all).

    Symbol-matched spans are masked with an equal-length run of spaces before
    the bare passes run, so an amount like "₹700 per person" is counted once
    (symbol pass) not twice — equal-length masking (rather than the previous
    single-space collapse) keeps every match offset aligned with `text` so
    the trailing-context unit check reads the right characters."""
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
        yield amount * rate, _has_daily_unit(text[m.end():m.end() + 20])

    for m in _BARE_AMOUNT_UNIT_SUFFIX_RE.finditer(masked):
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        # The unit phrase is inside this match; a trailing "per day" (e.g.
        # "500 per plate per day" would be odd, but "500 pp per day" isn't)
        # is also checked.
        is_daily = _has_daily_unit(m.group(0)) or _has_daily_unit(text[m.end():m.end() + 20])
        yield amount, is_daily

    for m in _PRICE_VERB_PREFIX_RE.finditer(masked):
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        is_daily = _has_daily_unit(m.group(0)) or _has_daily_unit(text[m.end():m.end() + 20])
        yield amount, is_daily


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
    when given, additionally requires the snippet to contain at least one
    on-topic word before any amount in it counts — guards against an
    in-bounds but off-topic amount (a club cover charge, a souvenir price)
    in a snippet that was retrieved for its overall topical similarity but
    isn't actually about the thing being priced. No filtering when omitted
    (existing callers unaffected).

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
        for raw, is_daily in _iter_raw_amounts(text):
            if per_day_meal_multiplier is not None and not is_daily:
                value = raw * per_day_meal_multiplier
            else:
                value = raw
            if low_bound <= value <= high_bound:
                amounts.append(value)
    return amounts


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
