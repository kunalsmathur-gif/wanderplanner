from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.validation import (
    MAX_BUDGET_AMOUNT,
    MAX_BUDGET_CATEGORIES,
    MAX_HOPS,
    MAX_KIDS,
    MAX_PER_GROUP_FIELD,
    MAX_PERSONAS,
    MAX_PREBOOKED_INR,
    MAX_STYLE_OPTIONS,
    MAX_THEMES,
    MAX_TRIP_DAYS,
    CityName,
    CountryName,
    CrowdPreference,
    CurrencyCode,
    DestinationMode,
    IataCode,
    Latitude,
    Longitude,
    OptionalCityName,
    Pace,
    PoiName,
    PurposeText,
    ShortLabel,
    TripScope,
    clean_trip_dates,
)

# Cap on verified must-include places carried on a trip config — keeps the
# PINNED prompt block bounded and leaves the LLM room to plan around them.
MAX_PINNED_POIS = 8

# Free-text and collection bounds live in core/validation.py — every field
# below that a user can type into is one of its constrained types, because
# each of them reaches the Gemini prompt and (for destinations) Nominatim and
# Overpass. See that module's docstring for what was accepted before.


class KidAge(BaseModel):
    age: int = Field(ge=2, le=17)


class GroupComposition(BaseModel):
    infants: int = Field(default=0, ge=0, le=MAX_PER_GROUP_FIELD)       # 0-2 years
    kids: list[KidAge] = Field(default_factory=list, max_length=MAX_KIDS)  # 2-17 years

    @field_validator('kids', mode='before')
    @classmethod
    def coerce_kids(cls, v: object) -> object:
        """Accept plain integers from LLM: [3, 6] → [{"age": 3}, {"age": 6}]."""
        if isinstance(v, list):
            return [{'age': k} if isinstance(k, int) else k for k in v]
        return v
    adults: int = Field(default=1, ge=0, le=MAX_PER_GROUP_FIELD)        # 8+ years
    seniors: int = Field(default=0, ge=0, le=MAX_PER_GROUP_FIELD)       # 60+ years
    pets: int = Field(default=0, ge=0, le=MAX_PER_GROUP_FIELD)

    @property
    def has_kids(self) -> bool:
        return len(self.kids) > 0

    @property
    def has_young_kids(self) -> bool:
        """Any child under 5 — triggers auto-Relaxed pace."""
        return any(k.age < 5 for k in self.kids)

    @property
    def has_infants(self) -> bool:
        return self.infants > 0


class AccommodationPrefs(BaseModel):
    style: list[ShortLabel] = Field(default_factory=list, max_length=MAX_STYLE_OPTIONS)
    min_bedrooms: int = Field(default=1, ge=0, le=20)
    bathrooms: int = Field(default=1, ge=0, le=20)
    private_pool: bool = False
    kitchen: bool = False
    wheelchair_accessible: bool = False
    pet_friendly: bool = False


class Budget(BaseModel):
    amount: float = Field(ge=0, le=MAX_BUDGET_AMOUNT)
    currency: CurrencyCode = "USD"


class DestinationInput(BaseModel):
    city: CityName
    country: CountryName = ""
    lat: Latitude = 0.0
    lon: Longitude = 0.0


class OriginInput(BaseModel):
    # Origin is optional in a way destination isn't: TripConfig's default is a
    # blank origin, and the wizard fills it in later (core/budget_estimator.py
    # gates flight costing on it being present).
    city: OptionalCityName = ""
    iata: IataCode = ""
    lat: Latitude = 0.0
    lon: Longitude = 0.0


class PinnedPOI(BaseModel):
    """A verified must-include place (⭐ NEW — refinement hard-constraints,
    docs/GTM_STRATEGY.md §2 "Harry Potter test").

    Only ever created by services/poi_pinning.py after the candidate has been
    confirmed against ingested OSM POIs (coords attached) or Wikivoyage text
    (existence only) — an unverified name can never become a pin.
    """
    name: PoiName
    lat: Latitude = 0.0
    lon: Longitude = 0.0
    poi_type: ShortLabel = ""
    source_interest: ShortLabel = ""   # the named interest that produced it, e.g. "Harry Potter"
    verified_by: ShortLabel = "osm"    # "osm" (coords are real) | "wiki" (existence confirmed, coords unknown)


class DayCostPreference(BaseModel):
    """"Make day 3 cheaper" — a spend steer for one day of the itinerary.

    Only ever created server-side from a refinement turn (see
    chains/chat_refine_chain.py), never authored by the LLM as free text.
    """
    day_number: int = Field(ge=1, le=MAX_TRIP_DAYS)
    # "cheaper" is the case that prompted this; "pricier" is its exact mirror
    # and costs nothing to support ("splurge on the last night"). Anything
    # outside the pair is rejected rather than coerced — unlike the wizard's
    # enum fields, the producer here is our own deterministic parser, so a bad
    # value is a bug in our code, not model drift to be tolerated.
    direction: Literal["cheaper", "pricier"]


class TripConfig(BaseModel):
    purpose: PurposeText = ""
    # Shape-validated by core.validation.clean_trip_dates, not modelled — a
    # dozen call sites read this with `.get()`. Kept a dict on purpose; see
    # that function's docstring.
    dates: dict = Field(default_factory=lambda: {"start": None, "end": None, "flexible": False})  # {"start": "YYYY-MM-DD" | null, "end": "YYYY-MM-DD" | null, "flexible": bool}
    # The four closed-set fields below normalise before validating (see
    # core/validation.py's "Closed-set (enum-ish) fields" block): "Moderate",
    # "off-beat" and "undecided" are accepted and canonicalised rather than
    # 422'd, because the producer is the wizard LLM, not a user typing.
    scope: TripScope = "international"
    origin: OriginInput = Field(default_factory=lambda: OriginInput(city="", lat=0, lon=0))
    destination: DestinationInput | None = None
    destination_mode: DestinationMode = "fixed"
    destination_country: CountryName | None = None  # used when mode = "country"
    # `max_length` enforces what the comment has always claimed and what the
    # frontend store already does (tripConfigStore.ts caps at 5). Each hop is
    # its own cold-start ingestion — Overpass, Wikivoyage and embeddings — so
    # an uncapped list is a per-request multiplier on the slowest path there is.
    hops: list[DestinationInput] = Field(default_factory=list, max_length=MAX_HOPS)  # multi-stop, max 5
    themes: list[ShortLabel] = Field(default_factory=list, max_length=MAX_THEMES)
    personas: list[ShortLabel] = Field(default_factory=list, max_length=MAX_PERSONAS)
    group: GroupComposition = Field(default_factory=GroupComposition)
    accommodation: AccommodationPrefs = Field(default_factory=AccommodationPrefs)
    pace: Pace = "moderate"
    # Crowd dial (⭐ NEW — hidden-gem curation, docs/GTM_STRATEGY.md §2):
    # "touristy" = iconic must-sees | "balanced" = mix | "offbeat" = prefer
    # community-verified hidden gems, de-prioritise crowd-heavy spots.
    crowd_preference: CrowdPreference = "balanced"
    budget: Budget = Field(default_factory=lambda: Budget(amount=0, currency="USD"))
    # Optional per-category budget steering (⭐ NEW — budget curation).
    # Values from: "accommodation" | "food" | "activities" | "shopping" | "local_transport"
    splurge_categories: list[ShortLabel] = Field(default_factory=list, max_length=MAX_BUDGET_CATEGORIES)
    save_categories: list[ShortLabel] = Field(default_factory=list, max_length=MAX_BUDGET_CATEGORIES)
    # Already-paid flight/accommodation costs (⭐ NEW — user explicitly states
    # they've already booked these; the real amount replaces our heuristic
    # estimate for that cost component in budget recommendations/feasibility).
    prebooked_flights_inr: int | None = Field(default=None, ge=0, le=MAX_PREBOOKED_INR)
    prebooked_accommodation_inr: int | None = Field(default=None, ge=0, le=MAX_PREBOOKED_INR)
    # Verified must-include places from named-interest refinements (⭐ NEW —
    # "Harry Potter test"). Hard constraints in the generation prompt, not
    # suffix nudges. Capped to keep the prompt block and the itinerary sane.
    pinned_pois: list[PinnedPOI] = Field(default_factory=list)
    # Per-day spend steering from refinement ("make day 3 cheaper"). Structured
    # rather than free text on purpose: the alternative is threading the user's
    # raw sentence into the generation prompt, which is both an injection
    # surface and unbounded. A closed direction set means the prompt block is
    # authored by us and the model only chooses places.
    day_cost_preferences: list[DayCostPreference] = Field(default_factory=list)

    @field_validator('pinned_pois')
    @classmethod
    def cap_pinned_pois(cls, v: list[PinnedPOI]) -> list[PinnedPOI]:
        return v[:MAX_PINNED_POIS]

    @field_validator('day_cost_preferences')
    @classmethod
    def dedupe_day_cost_preferences(cls, v: list[DayCostPreference]) -> list[DayCostPreference]:
        """Last write wins per day, and the list can never outgrow the trip.

        Refinement is iterative — "make day 3 cheaper" then "actually splurge
        on day 3" must leave ONE preference for day 3, not two contradictory
        ones the prompt would have to arbitrate.
        """
        by_day: dict[int, DayCostPreference] = {}
        for pref in v:
            by_day[pref.day_number] = pref
        return [by_day[d] for d in sorted(by_day)][:MAX_TRIP_DAYS]

    @field_validator('dates', mode='before')
    @classmethod
    def validate_dates(cls, v: Any) -> dict[str, Any]:
        return clean_trip_dates(v)

    def effective_pace(self) -> str:
        """Auto-apply Relaxed if any kid is under 5."""
        if self.group.has_young_kids and self.pace != "packed":
            return "relaxed"
        return self.pace

    def effective_duration_days(self) -> int | None:
        """Trip length in days, or None when it genuinely isn't known yet.

        `dates` is a dict and `duration_days` only appears in it when the
        wizard captured a length explicitly ("about a week"); a trip given
        concrete start/end dates has no such key. Reading `duration_days`
        alone therefore returns None for most real trips — which is how the
        `itinerary_generated` analytics event came to record `days: null`.

        ⚠️ Returns None rather than a default. `chains/recommend_cities_chain.py
        ::_calc_days` falls back to 7 for the same computation, which is right
        for prompt-building — a plausible number beats none — and wrong for
        analytics, where a fabricated 7 is indistinguishable from a real one.
        """
        explicit = self.dates.get("duration_days")
        if explicit is not None:
            return int(explicit)
        start, end = self.dates.get("start"), self.dates.get("end")
        if not start or not end:
            return None
        try:
            return max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days)
        except (TypeError, ValueError):
            return None
