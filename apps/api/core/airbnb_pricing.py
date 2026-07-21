"""Per-city hotel-equivalent nightly rates derived from real Inside Airbnb
"entire home/apt" listing data (CC BY 4.0 licensed, https://insideairbnb.com
— commercial use permitted with attribution), used as a destination-specific
fallback in `core/budget_estimator.py` when community RAG grounding
(Reddit/Wikivoyage/YouTube comments) has no signal for a city AND Wikivoyage
itself has no usable inline hotel-pricing data for it either — i.e. before
falling all the way back to the generic same-tier flat _COST_MATRIX number.

Each entry = (Inside Airbnb median "entire home/apt" nightly price, halved
for double occupancy) ÷ `_AIRBNB_STAY_DISCOUNT_MULTIPLIER` (see
core/budget_estimator.py, ≈0.30) to approximate a hotel-equivalent rate,
since raw whole-apartment Airbnb prices run cheaper than hotel rooms in the
same market (see that constant's docstring for how the 0.30 figure itself
was derived). This is a manually-seeded, extend-as-you-go list, not a live
per-request Airbnb fetch — downloading/parsing a city's full listings CSV
(tens of thousands of rows) is too slow to do inside a request path, and
Inside Airbnb only covers ~100 cities globally, so a live "does this
destination exist" check would fail silently for most destinations anyway.
Extend this dict using `scripts/ingest_airbnb_pricing.py`, which prints a
paste-ready entry for a given Inside Airbnb city/date snapshot — don't
hand-compute ratios here.
"""
from __future__ import annotations

# city name (lowercased, matched as a substring of "city country") -> hotel-
# equivalent INR per person per night.
AIRBNB_HOTEL_EQUIVALENT_PP_INR: dict[str, int] = {
    # Istanbul: 2026-07-22 check found no consolidated inline Wikivoyage
    # hotel-price listing (the article's Sleep section doesn't carry the
    # per-listing {{sleep}} price templates the way Bangkok/Paris/Athens/
    # Rome district pages do), so this is the only real anchor available.
    # Source: Inside Airbnb turkey/marmara/istanbul snapshot (2026-06-30),
    # n=16,285 entire-home listings, median ₺3,500/night whole apt.
    # ₺3,500 ÷ 2 (double occ) = ₺1,750/pp. TRY->INR via USD cross rate
    # (live 2026-07-21 check: USD/TRY≈47.19, vs. core/config.py's
    # usd_to_inr_rate=87.0 USD/INR) => ₺1 ≈ ₹1.844 => ₹3,227/pp raw Airbnb.
    # ÷ 0.30 hotel-equivalent multiplier => ₹10,757/pp hotel-equivalent (script output).
    "istanbul": 10757,
}


def airbnb_hotel_equivalent_pp_inr(city: str | None, country: str | None) -> int | None:
    """Best-effort city-name lookup (case-insensitive substring match against
    "city country") — returns None if this destination isn't in the seed
    list yet, so the caller should fall back further (flat _COST_MATRIX)."""
    haystack = f"{city or ''} {country or ''}".lower().strip()
    if not haystack:
        return None
    for key, value in AIRBNB_HOTEL_EQUIVALENT_PP_INR.items():
        if key in haystack:
            return value
    return None
