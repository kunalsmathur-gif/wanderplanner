from __future__ import annotations

from pydantic import BaseModel, Field

from core.validation import MAX_COMPARED_DESTINATIONS, MAX_TRIP_DAYS, ShortLabel
from models.trip import DestinationInput, TripConfig


class ItineraryItemLocation(BaseModel):
    lat: float
    lon: float
    address: str = ""


class TransitWarning(BaseModel):
    between_items: list[str]
    message: str


class ItineraryItem(BaseModel):
    id: str
    time_start: str
    time_end: str
    title: str
    local_name: str = ""   # Place name in local script/language (e.g. 浅草寺 for Senso-ji)
    description: str
    location: ItineraryItemLocation
    tags: list[str] = Field(default_factory=list)
    # Out-of-pocket cost of doing this one thing, for the WHOLE GROUP, in INR:
    # entry/ticket price, the meal, the ride. 0 means genuinely free (a beach,
    # a walk, a temple with no entry fee) — unlike ExpenseBreakdown.visa_inr,
    # there is no "unknown" state here, because a per-item figure is only ever
    # an estimate and a null would give callers a third case to handle for no
    # benefit. Deliberately EXCLUDES flights and accommodation: those are
    # trip-level, and folding them into a day would make every day containing
    # a hotel check-in look artificially expensive.
    #
    # This exists so a day has a summable cost at all — without it "make day 3
    # cheaper" has nothing to move and nothing to show (see
    # TripConfig.day_cost_preferences).
    estimated_cost_inr: int = Field(default=0, ge=0, le=10_000_000)
    booking_url: str = ""
    youtube_video_id: str = ""
    youtube_search_query: str = ""
    alignment_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    # True unless the live-generation post-processing pass could not match this
    # item's title against our ingested OSM/wiki corpus for the destination —
    # meaning the LLM likely recalled it from training data, not from anything
    # Wanderplanner has verified. Defaults to True (not False) so items from
    # paths that never run the check (mock, cache, rag_skeleton — all already
    # either curated or OSM-sourced by construction) read as verified rather
    # than silently "unknown", mirroring the visa_inr null-vs-zero discipline:
    # a field must never look ambiguous between "checked and fine" and
    # "never checked at all".
    verified: bool = True
    # True when this item's coordinates sit implausibly far from the trip's
    # destination (e.g. "Warner Bros Studio Tour, London" suggested for a
    # Bali trip) — a stronger, more specific defect than plain "verified":
    # this is a real, matchable place that is simply the wrong place, not an
    # unconfirmed one. Kept as its own flag rather than folded into
    # `verified=False` because the two need different user-facing language
    # (and different confidence — this one is a near-certain geocoding/LLM
    # mistake, not "we just haven't ingested this yet").
    out_of_bounds: bool = False


class ItineraryDay(BaseModel):
    day_number: int
    date: str
    theme: str
    items: list[ItineraryItem] = Field(default_factory=list)

    @property
    def estimated_cost_inr(self) -> int:
        """What this day costs the group, in INR — the sum of its items.

        A property rather than a stored field so it can never disagree with
        the items it is derived from (a stored total would drift the moment
        an item is added, dropped or re-costed during refinement).
        """
        return sum(item.estimated_cost_inr for item in self.items)
    transit_warnings: list[TransitWarning] = Field(default_factory=list)
    image_url: str = ""
    image_photographer: str = ""
    image_photographer_url: str = ""


class ExpenseBreakdown(BaseModel):
    """Estimated cost breakdown for the full trip, in INR."""
    flights_inr: int = 0           # Round-trip flights for all passengers
    # ⚠️ `None` means "we could not look this up", NOT "free". 0 means we
    # checked and entry genuinely costs nothing. Collapsing the two is exactly
    # how a 5-day Bhutan trip came to show ₹41,000 of "visa" — an ungrounded
    # guess is indistinguishable from a real figure once it is an int. The
    # frontend renders None as "not available" so the traveller knows to look
    # it up rather than reading silence as free entry.
    visa_inr: int | None = None    # Total visa/entry fees; None = unknown
    accommodation_inr: int = 0     # Accommodation for all nights
    activities_inr: int = 0        # Entry passes & tickets for itinerary activities
    food_inr: int = 0              # Food & dining for full trip
    local_transport_inr: int = 0   # In-destination transport
    shopping_inr: int = 0          # Souvenirs & shopping estimate
    emergency_buffer_inr: int = 0  # Recommended 10% emergency buffer
    total_inr: int = 0
    destination_currency_code: str = ""   # e.g. "JPY"
    total_destination_currency: int = 0   # approximate total in destination currency
    num_people: int = 1


class ItineraryResponse(BaseModel):
    days: list[ItineraryDay]
    alignment_score: float
    warnings: list[str] = Field(default_factory=list)
    expense_breakdown: ExpenseBreakdown = Field(default_factory=ExpenseBreakdown)
    # "live" = real LLM generation, grounded in retrieved destination research
    # (the verified-data path). "live_unverified" = the LLM call itself
    # succeeded, but retrieve_context() came back empty for this destination
    # (no ingested OSM/wiki/Reddit data), so the model fell back to its own
    # training knowledge for the entire itinerary with no corpus to check it
    # against — never present that as equivalent to "live". Anything else
    # means generate_itinerary degraded to a fallback tier (docs §4) — the
    # client must disclose this, never present a fallback plan as verified.
    # One of: "live", "live_unverified", "cache", "rag_skeleton",
    # "enhanced_mock", "mock".
    generation_tier: str = "live"



class GenerateItineraryRequest(BaseModel):
    trip_config: TripConfig


class LastItineraryResponse(BaseModel):
    """`GET /me/last-itinerary` response — the trip config paired with the
    itinerary it produced, so the client can load both straight into the
    existing wizard/edit flow (tripConfigStore + itineraryStore) with no
    separate lookup."""
    trip_config: TripConfig
    itinerary: ItineraryResponse
    updated_at: str


class DayPhotosRequest(BaseModel):
    """Hero photos for the PDF export, fetched on demand.

    These used to be attached during generation, which put a metered
    third-party call on the critical path of every itinerary for images the
    dashboard never rendered — only the PDF uses them. Now the client asks for
    them when the user actually presses Download.

    One Pexels call per query, so length is a direct cost multiplier: bounded
    by `MAX_TRIP_DAYS` for the same reason `CompareDestinationsRequest` bounds
    its destination list.
    """
    queries: list[ShortLabel] = Field(default_factory=list, max_length=MAX_TRIP_DAYS)


class DayPhoto(BaseModel):
    url: str = ""
    photographer: str = ""
    photographer_url: str = ""


class CompareDestinationsRequest(BaseModel):
    # services/comparison.py does per-destination work (geocode, budget
    # estimate, RAG lookups) for every entry, so the list length is a direct
    # multiplier on the request's cost.
    destinations: list[DestinationInput] = Field(default_factory=list, max_length=MAX_COMPARED_DESTINATIONS)
    trip_config: TripConfig


class ComparisonParameter(BaseModel):
    parameter: str
    unit: str = ""
    values: dict[str, str | float]
    winner: str = ""
    highlight: str = ""  # "" | "winner" | "bottleneck"


class ComparisonResponse(BaseModel):
    comparison: list[ComparisonParameter]
    partial_failures: list[str] = Field(default_factory=list)
