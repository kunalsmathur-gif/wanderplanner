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
    published_date: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]


class GeocodeResponse(BaseModel):
    display_name: str
    lat: float
    lon: float
    country_code: str
    is_country: bool = False
    # 🔴 True when this is a region/country-level centroid that we WANTED to
    # correct to its hub town but could not, because the Overpass lookup that
    # does the correcting errored or was throttled. It is NOT set when Overpass
    # answered and there genuinely is no town, nor when the bbox was too large
    # to query — in both of those cases the centroid is the honest best answer.
    #
    # The distinction exists because the two are indistinguishable at the
    # coordinates alone, and acting on the second silently ingests data for the
    # wrong part of the map: Bali's stored POIs sat 48km from Denpasar, in the
    # wrong half of the island, written by exactly such a run (2026-08-05).
    # Callers that persist anything keyed on these coordinates must check this
    # — see scrapers/osm.py::ingest_osm_pois.
    hub_lookup_degraded: bool = False
    # Nominatim's bounding box for the matched place, as (south, north, west,
    # east). Carried so callers can tell how BIG this destination is: a single
    # centre point says nothing about whether "Goa" is a town or a 105km-long
    # state, and ingesting a large one from one centre misses everything past
    # its radius. See scrapers/osm.py::_area_centroids.
    bbox: tuple[float, float, float, float] | None = None
