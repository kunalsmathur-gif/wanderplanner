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
    # 2026-07-30 (issue #56): extended beyond the single Istanbul anchor.
    # Each of these was verified live via `action=parse` to have NO
    # {{sleep}} price-template listings in its Wikivoyage "Sleep" section
    # (unlike Paris/Bangkok/Tokyo/Rome/Cape Town/Nairobi, which do carry
    # inline templated hotel pricing and so don't need this fallback) —
    # same "Wikivoyage has no usable inline hotel-pricing data" gap
    # Istanbul was seeded for. FX rates are live spot rates from
    # https://open.er-api.com/v6/latest/USD (2026-07-30), and all computed
    # via `scripts/ingest_airbnb_pricing.py` against each city's Inside
    # Airbnb `visualisations/listings.csv` snapshot (median entire-home/apt
    # nightly price -> INR -> /2 double occ -> /0.30 hotel-equivalent).
    # Mexico City: MXN, n=19,856 listings, snapshot 2026-06-15, USD/MXN=17.4627.
    "mexico city": 17960,
    # Rio de Janeiro: BRL, n=36,153 listings, snapshot 2026-06-24, USD/BRL=5.1199.
    "rio de janeiro": 13849,
    # Vienna: EUR, n=9,132 listings, snapshot 2026-06-20, USD/EUR=0.8756.
    "vienna": 20701,
    # Oslo: NOK, n=8,689 listings, snapshot 2026-06-30, USD/NOK=9.6349.
    "oslo": 29196,
    # Toronto: CAD, n=12,500 listings, snapshot 2026-06-15, USD/CAD=1.4062.
    "toronto": 27325,
    # Sydney: AUD, n=13,831 listings, snapshot 2026-06-16, USD/AUD=1.4384.
    "sydney": 34577,
    # Buenos Aires: ARS, n=25,141 listings, snapshot 2026-06-29, USD/ARS=1496.3521.
    "buenos aires": 10076,
    # Stockholm: SEK, n=2,634 listings, snapshot 2026-06-30, USD/SEK=9.6849.
    "stockholm": 34091,
    # São Paulo: BRL, n=35,984 listings, snapshot 2026-06-14, USD/BRL=5.1199.
    "são paulo": 9714,
    # Bogotá: COP, n=13,744 listings, snapshot 2026-06-21, USD/COP=3207.6378.
    "bogotá": 8254,
    # Santiago: CLP, n=14,425 listings, snapshot 2026-06-29, USD/CLP=934.0608.
    "santiago": 10075,
    # Riga: EUR, n=2,903 listings, snapshot 2026-06-30, USD/EUR=0.8756.
    "riga": 13911,
    # Vancouver: CAD, n=4,796 listings, snapshot 2026-06-15, USD/CAD=1.4062.
    "vancouver": 36812,
    # Montreal: CAD, n=7,746 listings, snapshot 2026-06-15, USD/CAD=1.4062.
    "montreal": 18973,
    # Melbourne: AUD, n=14,472 listings, snapshot 2026-06-16, USD/AUD=1.4384.
    "melbourne": 28327,
    # 2026-07-30 (issue #56 follow-up): second batch, same methodology —
    # each of these 15 was live-verified via `action=parse` to have ZERO
    # {{sleep}} price templates in its Wikivoyage "Sleep" section (checked
    # alongside Dublin/Florence/Lyon/Porto/Rome/Seville/Valencia/Venice,
    # which DO carry templates and so are excluded as non-gaps).
    # Barcelona: EUR, n=10,114 listings, snapshot 2026-06-24, USD/EUR=0.8756.
    "barcelona": 36764,
    # Berlin: EUR, n=6,138 listings, snapshot 2026-06-26, USD/EUR=0.8756.
    "berlin": 25834,
    # Copenhagen: DKK, n=12,779 listings, snapshot 2026-06-30, USD/DKK=6.5401.
    "copenhagen": 38600,
    # Edinburgh: GBP, n=3,990 listings, snapshot 2026-06-23, USD/GBP=0.7507.
    "edinburgh": 53889,
    # Hong Kong: HKD, n=2,208 listings, snapshot 2026-06-27, USD/HKD=7.8421.
    "hong kong": 18259,
    # Lisbon: EUR, n=16,881 listings, snapshot 2026-06-23, USD/EUR=0.8756.
    "lisbon": 26000,
    # London: GBP, n=42,123 listings, snapshot 2026-06-19, USD/GBP=0.7507.
    "london": 46356,
    # Los Angeles: USD, n=28,437 listings, snapshot 2026-06-15.
    "los angeles": 40890,
    # Madrid: EUR, n=13,936 listings, snapshot 2026-06-20, USD/EUR=0.8756.
    "madrid": 23847,
    # Milan: EUR, n=20,337 listings, snapshot 2026-06-25, USD/EUR=0.8756.
    "milan": 23185,
    # Munich: EUR, n=2,839 listings, snapshot 2026-06-29, USD/EUR=0.8756.
    "munich": 30140,
    # New York: USD, n=11,537 listings, snapshot 2026-06-14. Keyed "new york"
    # (not "new york city") to match this app's destination naming
    # (scrapers/reddit.py's KNOWN_DESTINATIONS uses "New York").
    "new york": 32335,
    # Prague: CZK, n=8,860 listings, snapshot 2026-06-27, USD/CZK=21.188.
    "prague": 18176,
    # San Francisco: USD, n=3,513 listings, snapshot 2026-06-14.
    "san francisco": 43210,
    # Washington DC: USD, n=4,618 listings, snapshot 2026-06-24.
    "washington dc": 33785,
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
