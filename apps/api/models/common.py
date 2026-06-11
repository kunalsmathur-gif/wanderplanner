from __future__ import annotations
from pydantic import BaseModel, Field


class MonthlyWeather(BaseModel):
    month: str
    avg_temp_c: float
    avg_rain_mm: float
    sunshine_hours: float


class BusyPeriod(BaseModel):
    months: list[str]
    label: str
    source: str  # "wikivoyage" | "wikipedia" | "osm"


class LocalEvent(BaseModel):
    name: str
    month: str
    duration_days: int = 0
    source: str


class BestTimeResponse(BaseModel):
    destination: str
    monthly_weather: list[MonthlyWeather] = Field(default_factory=list)
    busy_periods: list[BusyPeriod] = Field(default_factory=list)
    best_months: list[str] = Field(default_factory=list)
    avoid_months: list[str] = Field(default_factory=list)
    peak_season: str = ""
    off_season: str = ""
    weather_summary: str = ""
    events: list[LocalEvent] = Field(default_factory=list)


class SearchResult(BaseModel):
    text: str
    source: str
    source_url: str
    score: float
    destination: str


class SearchResponse(BaseModel):
    results: list[SearchResult]


class GeocodeResponse(BaseModel):
    display_name: str
    lat: float
    lon: float
    country_code: str
