"""Deterministic (no-LLM) price extraction from free-text community snippets.

Used by `core/budget_estimator.py` to ground the stay/food components in
real per-destination data pulled from the app's existing free RAG
collections (Reddit/Wikivoyage via `core/cost_grounding.py`) when it's
actually there, without reintroducing LLM guessing — which is exactly the
failure mode `core/budget_estimator.py` exists to avoid (see its module
docstring). A regex/median extraction is a blunt instrument on messy
traveller prose, so it only overrides the hand-authored default when it
finds enough plausible amounts (`min_samples`) inside a sane bound — a
single stray number is not treated as a real signal.
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
