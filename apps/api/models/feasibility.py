from __future__ import annotations
from pydantic import BaseModel, Field
from models.trip import TripConfig


class CostBreakdown(BaseModel):
    flights_inr: int = 0           # Return flights per person × num people
    visa_inr: int = 0              # Total visa fees
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
    alternatives: list[AlternativeDestination] = Field(default_factory=list)
    disclaimer: str = "Cost estimates are approximate and based on average market rates."


class FeasibilityRequest(BaseModel):
    trip_config: TripConfig
