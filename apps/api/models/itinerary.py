from __future__ import annotations
from pydantic import BaseModel, Field
from models.trip import TripConfig, DestinationInput


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
    booking_url: str = ""
    youtube_video_id: str = ""
    youtube_search_query: str = ""
    alignment_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day_number: int
    date: str
    theme: str
    items: list[ItineraryItem] = Field(default_factory=list)
    transit_warnings: list[TransitWarning] = Field(default_factory=list)


class ExpenseBreakdown(BaseModel):
    """Estimated cost breakdown for the full trip, in INR."""
    flights_inr: int = 0           # Round-trip flights for all passengers
    visa_inr: int = 0              # Total visa/entry fees
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



class GenerateItineraryRequest(BaseModel):
    trip_config: TripConfig


class CompareDestinationsRequest(BaseModel):
    destinations: list[DestinationInput]
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
