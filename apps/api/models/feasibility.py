from __future__ import annotations

from pydantic import BaseModel, Field

from models.trip import TripConfig


class CostBreakdown(BaseModel):
    flights_inr: int = 0           # Return flights per person × num people
    # None = we could not look it up; 0 = checked, genuinely free. See the
    # matching note on `models/itinerary.py::ExpenseBreakdown.visa_inr`.
    visa_inr: int | None = None    # Total visa/entry fees; None = unknown
    accommodation_inr: int = 0     # Nightly rate × nights × rooms
    daily_expenses_inr: int = 0    # Food + activities + local transport × days × people
    total_estimated_inr: int = 0


class AlternativeDestination(BaseModel):
    city: str
    country: str
    estimated_total_inr: int
    why_cheaper: str              # Short reason e.g. "No visa required, cheaper flights from India"
    similar_experiences: list[str] = Field(default_factory=list)


class FeasibilityResponse(BaseModel):
    feasible: bool
    verdict: str                  # One-line summary shown to user
    budget_inr: int
    breakdown: CostBreakdown
    shortfall_inr: int = 0        # 0 if feasible
    buffer_inr: int = 0           # remaining budget if feasible
    bare_minimum_inr: int | None = None  # deterministic flights+stay+food floor, when computable
    alternatives: list[AlternativeDestination] = Field(default_factory=list)
    disclaimer: str = "Cost estimates are approximate and based on average market rates."
    # None = destination existence wasn't checked (e.g. destination_mode is
    # "country" or "exploring", where there's no single named place to
    # geocode yet). False = geocoding (Nominatim + Wikipedia fallback, same
    # lookup used everywhere else in the app) found nothing for this name —
    # it may be misspelled, or it may be entirely fictional (the deck's
    # "Wizarding World Goa" case). This is a distinct, cheaper, earlier
    # check than budget feasibility: a nonexistent destination has no
    # meaningful cost to estimate at all, so this is checked first and can
    # short-circuit the LLM cost-estimation call entirely. Unlike the budget
    # gate, this is deliberately not a hard block — real places are
    # routinely missing from Nominatim/Wikipedia (a false negative here is
    # far more likely than a false positive), so the user is told and given
    # the choice to proceed anyway rather than being locked out.
    destination_verified: bool | None = None


class FeasibilityRequest(BaseModel):
    trip_config: TripConfig
    # When true, skip the destination-existence check even if it would
    # otherwise fail — set after the user has already seen the "we
    # couldn't verify this place" notice and chosen to continue anyway.
    skip_destination_check: bool = False
