from __future__ import annotations
from pydantic import BaseModel, Field, field_validator

# Cap on verified must-include places carried on a trip config — keeps the
# PINNED prompt block bounded and leaves the LLM room to plan around them.
MAX_PINNED_POIS = 8


class KidAge(BaseModel):
    age: int = Field(ge=2, le=17)


class GroupComposition(BaseModel):
    infants: int = Field(default=0, ge=0)       # 0-2 years
    kids: list[KidAge] = Field(default_factory=list)  # 2-17 years

    @field_validator('kids', mode='before')
    @classmethod
    def coerce_kids(cls, v: object) -> object:
        """Accept plain integers from LLM: [3, 6] → [{"age": 3}, {"age": 6}]."""
        if isinstance(v, list):
            return [{'age': k} if isinstance(k, int) else k for k in v]
        return v
    adults: int = Field(default=1, ge=0)        # 8+ years
    seniors: int = Field(default=0, ge=0)       # 60+ years
    pets: int = Field(default=0, ge=0)

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
    style: list[str] = Field(default_factory=list)
    min_bedrooms: int = 1
    bathrooms: int = 1
    private_pool: bool = False
    kitchen: bool = False
    wheelchair_accessible: bool = False
    pet_friendly: bool = False


class Budget(BaseModel):
    amount: float
    currency: str = "USD"


class DestinationInput(BaseModel):
    city: str
    country: str = ""
    lat: float = 0.0
    lon: float = 0.0


class OriginInput(BaseModel):
    city: str
    iata: str = ""
    lat: float = 0.0
    lon: float = 0.0


class PinnedPOI(BaseModel):
    """A verified must-include place (⭐ NEW — refinement hard-constraints,
    docs/GTM_STRATEGY.md §2 "Harry Potter test").

    Only ever created by services/poi_pinning.py after the candidate has been
    confirmed against ingested OSM POIs (coords attached) or Wikivoyage text
    (existence only) — an unverified name can never become a pin.
    """
    name: str
    lat: float = 0.0
    lon: float = 0.0
    poi_type: str = ""
    source_interest: str = ""   # the named interest that produced it, e.g. "Harry Potter"
    verified_by: str = "osm"    # "osm" (coords are real) | "wiki" (existence confirmed, coords unknown)


class TripConfig(BaseModel):
    purpose: str = ""
    dates: dict = Field(default_factory=lambda: {"start": None, "end": None, "flexible": False})  # {"start": "YYYY-MM-DD" | null, "end": "YYYY-MM-DD" | null, "flexible": bool}
    scope: str = "international"   # "local" | "domestic" | "international"
    origin: OriginInput = Field(default_factory=lambda: OriginInput(city="", lat=0, lon=0))
    destination: DestinationInput | None = None
    destination_mode: str = "fixed"  # "fixed" | "exploring" | "country"
    destination_country: str | None = None  # used when mode = "country"
    hops: list[DestinationInput] = Field(default_factory=list)  # multi-stop, max 5
    themes: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    group: GroupComposition = Field(default_factory=GroupComposition)
    accommodation: AccommodationPrefs = Field(default_factory=AccommodationPrefs)
    pace: str = "moderate"  # "relaxed" | "moderate" | "packed"
    # Crowd dial (⭐ NEW — hidden-gem curation, docs/GTM_STRATEGY.md §2):
    # "touristy" = iconic must-sees | "balanced" = mix | "offbeat" = prefer
    # community-verified hidden gems, de-prioritise crowd-heavy spots.
    crowd_preference: str = "balanced"  # "touristy" | "balanced" | "offbeat"
    budget: Budget = Field(default_factory=lambda: Budget(amount=0, currency="USD"))
    # Optional per-category budget steering (⭐ NEW — budget curation).
    # Values from: "accommodation" | "food" | "activities" | "shopping" | "local_transport"
    splurge_categories: list[str] = Field(default_factory=list)
    save_categories: list[str] = Field(default_factory=list)
    # Already-paid flight/accommodation costs (⭐ NEW — user explicitly states
    # they've already booked these; the real amount replaces our heuristic
    # estimate for that cost component in budget recommendations/feasibility).
    prebooked_flights_inr: int | None = None
    prebooked_accommodation_inr: int | None = None
    # Verified must-include places from named-interest refinements (⭐ NEW —
    # "Harry Potter test"). Hard constraints in the generation prompt, not
    # suffix nudges. Capped to keep the prompt block and the itinerary sane.
    pinned_pois: list[PinnedPOI] = Field(default_factory=list)

    @field_validator('pinned_pois')
    @classmethod
    def cap_pinned_pois(cls, v: list[PinnedPOI]) -> list[PinnedPOI]:
        return v[:MAX_PINNED_POIS]

    def effective_pace(self) -> str:
        """Auto-apply Relaxed if any kid is under 5."""
        if self.group.has_young_kids and self.pace != "packed":
            return "relaxed"
        return self.pace
