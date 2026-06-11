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
    description: str
    location: ItineraryItemLocation
    tags: list[str] = Field(default_factory=list)
    booking_url: str = ""
    youtube_video_id: str = ""
    alignment_score: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    day_number: int
    date: str
    theme: str
    items: list[ItineraryItem] = Field(default_factory=list)
    transit_warnings: list[TransitWarning] = Field(default_factory=list)


class ItineraryResponse(BaseModel):
    days: list[ItineraryDay]
    alignment_score: float
    warnings: list[str] = Field(default_factory=list)


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
