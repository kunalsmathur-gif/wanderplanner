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


def _extract_bare_inr_amounts(text: str) -> list[float]:
    """Extracts symbol-less amounts assumed to be INR, from unit-anchored or
    price-verb-anchored phrasing only (see module-level comment above the
    regexes). Runs on a copy of `text` with any already-symbol-matched spans
    blanked out first, so an amount like "₹700 per person" isn't double
    counted once via `_AMOUNT_RE` and again via the unit-suffix pattern."""
    masked = _AMOUNT_RE.sub(" ", text)
    amounts: list[float] = []
    for raw_amount in _BARE_AMOUNT_UNIT_SUFFIX_RE.findall(masked):
        try:
            amounts.append(float(raw_amount.replace(",", "")))
        except ValueError:
            continue
    for raw_amount in _PRICE_VERB_PREFIX_RE.findall(masked):
        try:
            amounts.append(float(raw_amount.replace(",", "")))
        except ValueError:
            continue
    return amounts


def extract_price_mentions_inr(snippets: list[str], low_bound: float, high_bound: float) -> list[float]:
    """Extracts plausible INR amounts from free-text snippets. Amounts
    outside [low_bound, high_bound] are discarded as implausible for the
    thing being estimated (e.g. a snippet mentioning a $500,000 house
    shouldn't be read as a nightly hotel rate)."""
    amounts: list[float] = []
    for text in snippets:
        for symbol, raw_amount, thousands_suffix in _AMOUNT_RE.findall(text):
            try:
                amount = float(raw_amount.replace(",", ""))
            except ValueError:
                continue
            rate = _FX_TO_INR.get(symbol.lower().rstrip("."))
            if rate is None:
                continue
            if thousands_suffix:
                amount *= 1000
            inr = amount * rate
            if low_bound <= inr <= high_bound:
                amounts.append(inr)
        for inr in _extract_bare_inr_amounts(text):
            if low_bound <= inr <= high_bound:
                amounts.append(inr)
    return amounts


def median_price_inr(
    snippets: list[str], low_bound: float, high_bound: float, min_samples: int = 2
) -> float | None:
    """Median of plausible price mentions found in `snippets`, or None if
    fewer than `min_samples` were found — too little signal to trust over
    the hand-authored default."""
    amounts = extract_price_mentions_inr(snippets, low_bound, high_bound)
    if len(amounts) < min_samples:
        return None
    return statistics.median(amounts)
