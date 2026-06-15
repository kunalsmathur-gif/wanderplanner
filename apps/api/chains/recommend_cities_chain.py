"""Recommend cities for a given country based on trip config."""
from __future__ import annotations

import asyncio
import json
from pydantic import BaseModel

from core.config import settings
from models.trip import TripConfig


class RecommendedCity(BaseModel):
    name: str
    country: str
    reason: str
    lat: float
    lon: float


class RecommendCitiesResponse(BaseModel):
    cities: list[RecommendedCity]


class RecommendCitiesRequest(BaseModel):
    country: str
    trip_config: TripConfig


_RECOMMEND_PROMPT = """\
You are a travel expert helping Indian tourists plan international trips.

Given the country and trip profile below, recommend 4-6 ideal cities to visit.
Consider: personas, budget (INR), trip duration, accommodation style, group composition, and themes.

Country: {country}
Trip profile:
{trip_profile}

Respond ONLY with a JSON array (no markdown, no explanation):
[
  {{
    "name": "City Name",
    "country": "Country Name",
    "reason": "One sentence why this city suits this traveller (mention 1-2 specific reasons from their profile)",
    "lat": 35.6762,
    "lon": 139.6503
  }},
  ...
]

Rules:
- Include variety: mix popular and offbeat, budget and premium options
- If budget is under ₹1,00,000 per person, prefer affordable cities
- If group has kids, prefer family-friendly cities
- Always include accurate lat/lon coordinates
- Return 4-6 cities only
"""


async def recommend_cities(request: RecommendCitiesRequest) -> RecommendCitiesResponse:
    if settings.llm_provider == "mock":
        return _mock_response(request.country)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    cfg = request.trip_config
    duration_days = _calc_days(cfg.dates)
    per_person = cfg.budget.amount / max(1, cfg.group.adults + cfg.group.seniors + len(cfg.group.kids))

    trip_profile = (
        f"- Duration: {duration_days} days\n"
        f"- Budget: ₹{cfg.budget.amount:,.0f} total (≈₹{per_person:,.0f}/person)\n"
        f"- Personas: {', '.join(cfg.personas) or 'not specified'}\n"
        f"- Themes: {', '.join(cfg.themes) or 'not specified'}\n"
        f"- Pace: {cfg.effective_pace()}\n"
        f"- Group: {cfg.group.adults} adults, {cfg.group.seniors} seniors, "
        f"{len(cfg.group.kids)} kids, {cfg.group.infants} infants\n"
        f"- Accommodation: {', '.join(cfg.accommodation.style) or 'any'}"
    )

    prompt = _RECOMMEND_PROMPT.format(
        country=request.country,
        trip_profile=trip_profile,
    )

    client = google_genai.Client(api_key=settings.gemini_api_key)

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(temperature=0.4, max_output_tokens=1024),
        )
        return response.text

    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, _call_sync)

    try:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        cities_data = json.loads(cleaned)
        cities = [RecommendedCity(**c) for c in cities_data[:6]]
        return RecommendCitiesResponse(cities=cities)
    except Exception:
        return _mock_response(request.country)


def _calc_days(dates: dict) -> int:
    try:
        from datetime import date
        s = date.fromisoformat(dates["start"])
        e = date.fromisoformat(dates["end"])
        return max(1, (e - s).days)
    except Exception:
        return 7


def _mock_response(country: str) -> RecommendCitiesResponse:
    defaults: dict[str, list[dict]] = {
        "japan": [
            {"name": "Tokyo", "country": "Japan", "reason": "World-class city with iconic sights, food, and culture", "lat": 35.6762, "lon": 139.6503},
            {"name": "Kyoto", "country": "Japan", "reason": "Best for temples, geishas, and traditional Japan — less crowded than Tokyo", "lat": 35.0116, "lon": 135.7681},
            {"name": "Osaka", "country": "Japan", "reason": "Foodie paradise and budget-friendlier than Tokyo", "lat": 34.6937, "lon": 135.5023},
        ],
        "france": [
            {"name": "Paris", "country": "France", "reason": "Iconic landmarks, art, and cuisine — unmissable first visit", "lat": 48.8566, "lon": 2.3522},
            {"name": "Nice", "country": "France", "reason": "Mediterranean coast, beaches, and relaxed pace", "lat": 43.7102, "lon": 7.2620},
            {"name": "Lyon", "country": "France", "reason": "Gastronomic capital, fewer tourists, more affordable", "lat": 45.7640, "lon": 4.8357},
        ],
    }
    key = country.lower()
    cities_data = defaults.get(key, [
        {"name": f"Capital of {country}", "country": country, "reason": "Primary city with best connectivity from India", "lat": 0.0, "lon": 0.0},
        {"name": f"Second city of {country}", "country": country, "reason": "Cultural hub with rich history", "lat": 0.0, "lon": 0.0},
    ])
    return RecommendCitiesResponse(cities=[RecommendedCity(**c) for c in cities_data])
