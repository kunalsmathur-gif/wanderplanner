"""Free-tools-only foreign-currency budget detection + deterministic INR conversion.

WanderPlanner's budget field is canonically stored and reasoned about in INR — the
wizard, feasibility check, and budget estimator all assume `budget.amount` is INR.
Previously this was an *implicit* assumption never surfaced to the user, and there
was no path for a user who naturally thinks in USD/EUR/etc. to state their budget
in their own currency.

This module:
  1. Detects when a user's own message states a budget in one of the top-10
     currencies WanderPlanner's Indian traveller base is most likely to use
     (regex-based, deterministic — never relies on the LLM to "do the math").
  2. Converts that amount to INR using the free, keyless Frankfurter.app API
     (same provider already used client-side for the dashboard currency widget),
     with a small in-memory TTL cache and a hardcoded fallback rate table so a
     network hiccup never blocks the wizard.
  3. Renders a short, ready-to-use prompt hint telling Anya the exact converted
     INR figure to use and mention — the LLM only phrases it, never computes it.

Best-effort throughout: any failure (network, parse, unknown currency) simply
results in `None`/`""`, and the wizard falls back to treating the number as INR.
"""

from __future__ import annotations

import re
import time

import httpx

# The 10 non-INR currencies Indian outbound travellers are most likely to
# reference when stating a budget in their own terms (major reserve/travel
# currencies + the most common regional/holiday destinations for Indian
# tourists: US, Eurozone, UK, UAE, Singapore, Australia, Canada, Japan,
# Thailand, Switzerland).
TOP_10_CURRENCIES = ["USD", "EUR", "GBP", "AED", "SGD", "AUD", "CAD", "JPY", "THB", "CHF"]

# Symbol / keyword aliases -> ISO code. Longest/most-specific keys checked first
# by the regex alternation (order matters for overlapping words like "dollars").
_ALIASES: dict[str, str] = {
    "$": "USD", "usd": "USD", "us dollar": "USD", "us dollars": "USD", "dollar": "USD", "dollars": "USD",
    "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "sterling": "GBP",
    "aed": "AED", "dirham": "AED", "dirhams": "AED",
    "sgd": "SGD", "singapore dollar": "SGD", "singapore dollars": "SGD",
    "aud": "AUD", "australian dollar": "AUD", "australian dollars": "AUD",
    "cad": "CAD", "canadian dollar": "CAD", "canadian dollars": "CAD",
    "¥": "JPY", "jpy": "JPY", "yen": "JPY",
    "thb": "THB", "baht": "THB",
    "chf": "CHF", "swiss franc": "CHF", "swiss francs": "CHF",
}

# Approximate fallback rates (1 unit of currency -> INR), used only if the
# live Frankfurter.app call fails. Deliberately approximate — always prefer
# the live rate; this exists purely so a network hiccup never blocks the wizard.
_FALLBACK_RATES_TO_INR: dict[str, float] = {
    "USD": 86.5, "EUR": 94.0, "GBP": 110.0, "AED": 23.5, "SGD": 64.5,
    "AUD": 57.0, "CAD": 62.5, "JPY": 0.58, "THB": 2.5, "CHF": 98.0,
}

_RATE_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours — exchange rates don't need to be second-fresh
_rate_cache: dict[str, tuple[float, float]] = {}  # currency -> (rate_to_inr, fetched_at_epoch)


def _build_amount_currency_pattern() -> re.Pattern:
    """Matches things like "$2000", "2000 USD", "2,000 dollars", "€1500", "AED 5000"."""
    alias_alt = "|".join(sorted((re.escape(a) for a in _ALIASES), key=len, reverse=True))
    number = r"(\d[\d,]*(?:\.\d+)?)\s*(?:k|K)?"
    # symbol-before-number (e.g. "$2000") or number-before-word (e.g. "2000 dollars")
    return re.compile(
        rf"(?:(?P<sym>{alias_alt})\s*{number})|(?:{number}\s*(?P<word>{alias_alt}))",
        re.IGNORECASE,
    )


_PATTERN = _build_amount_currency_pattern()

# Symbols that should never be treated as "k = thousand" shorthand ambiguity
_SYMBOL_ALIASES = {"$", "€", "£", "¥"}


def detect_foreign_currency(text: str | None) -> tuple[float, str] | None:
    """Best-effort scan of a user's own message for an amount stated in one of
    the top-10 supported non-INR currencies. Returns (amount, iso_currency) or
    None if nothing recognizable is found. Explicitly ignores INR/₹/rupees/
    lakh/crore phrasing — that's handled by the existing Section-2 parsing
    rules in the wizard prompt."""
    if not text:
        return None
    lowered = text.lower()
    if "₹" in text or "inr" in lowered or "rupee" in lowered or "rupees" in lowered:
        return None
    if "lakh" in lowered or "lac" in lowered or " cr" in lowered or "crore" in lowered:
        return None

    match = _PATTERN.search(text)
    if not match:
        return None

    alias_raw = (match.group("sym") or match.group("word") or "").lower().strip()
    currency = _ALIASES.get(alias_raw)
    if not currency or currency not in TOP_10_CURRENCIES:
        return None

    # The number is whichever unnamed numbered group matched (the regex has
    # two, one per alternation branch — symbol-first vs. word-first).
    num_str = None
    for g in match.groups():
        if g and re.match(r"^\d", g):
            num_str = g
            break
    if not num_str:
        return None

    try:
        amount = float(num_str.replace(",", ""))
    except ValueError:
        return None

    # "k" shorthand only makes sense for word-form currencies typed by a human
    # (e.g. "2k dollars"); symbol form ("$2k") is covered by the same number group.
    if re.search(rf"{re.escape(num_str)}\s*k\b", text, re.IGNORECASE):
        amount *= 1000

    if amount <= 0:
        return None
    return (amount, currency)


def _fetch_live_rate_to_inr(currency: str) -> float | None:
    """Calls the free, keyless Frankfurter.app API for a single-currency ->
    INR rate. Returns None on any failure (never raises)."""
    try:
        resp = httpx.get(
            "https://api.frankfurter.app/latest",
            params={"from": currency, "to": "INR"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data.get("rates", {}).get("INR")
        return float(rate) if rate else None
    except Exception:
        return None


def get_conversion_rate(currency: str) -> tuple[float, bool]:
    """Returns (rate_to_inr, was_live). Uses a 6-hour in-memory cache; falls
    back to a hardcoded approximate rate if the live API call fails."""
    currency = currency.upper()
    cached = _rate_cache.get(currency)
    now = time.time()
    if cached and (now - cached[1]) < _RATE_CACHE_TTL_SECONDS:
        return cached[0], True

    live_rate = _fetch_live_rate_to_inr(currency)
    if live_rate:
        _rate_cache[currency] = (live_rate, now)
        return live_rate, True

    return _FALLBACK_RATES_TO_INR.get(currency, 0.0), False


def convert_to_inr(amount: float, currency: str) -> dict | None:
    """Deterministically converts `amount` of `currency` to INR. Returns a
    dict with the original + converted figures, or None if the currency isn't
    supported / rate unavailable."""
    currency = currency.upper()
    if currency not in TOP_10_CURRENCIES:
        return None
    rate, is_live = get_conversion_rate(currency)
    if not rate:
        return None
    inr_amount = round(amount * rate)
    return {
        "original_amount": amount,
        "original_currency": currency,
        "inr_amount": inr_amount,
        "rate_to_inr": round(rate, 2),
        "rate_is_live": is_live,
    }


def currency_conversion_prompt_hint(hint_text: str | None) -> str:
    """Best-effort: scans the user's latest message for a foreign-currency
    budget statement and, if found, renders a ready-to-use prompt instruction
    with the exact deterministic INR conversion. Returns "" if nothing
    detected or on any internal error — the LLM should never be blocked by
    this and should fall back to treating any number as INR."""
    try:
        detected = detect_foreign_currency(hint_text)
        if not detected:
            return ""
        amount, currency = detected
        result = convert_to_inr(amount, currency)
        if not result:
            return ""
        rate_note = "today's live rate" if result["rate_is_live"] else "an approximate recent rate"
        return (
            f"The user stated their budget as {result['original_amount']:,.0f} {result['original_currency']}. "
            f"Using {rate_note} (1 {result['original_currency']} \u2248 \u20b9{result['rate_to_inr']}), this converts to "
            f"\u2248\u20b9{result['inr_amount']:,} INR. Set config_patch budget.amount to {result['inr_amount']} "
            f"and budget.currency to \"INR\" (INR is always the canonical stored currency). In your reply, "
            f"transparently mention both figures, e.g. \"Got it, {result['original_amount']:,.0f} "
            f"{result['original_currency']} is about \u20b9{result['inr_amount']:,} at today's rate.\" "
            f"Do not perform your own currency math — use this converted figure exactly."
        )
    except Exception:
        return ""
