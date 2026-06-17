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
        print("⚠️ google-genai not installed, using mock")
        return _mock_response(request.country)

    if not settings.gemini_api_key:
        print("⚠️ GEMINI_API_KEY not set, using mock")
        return _mock_response(request.country)

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

    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, _call_sync)

        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        cities_data = json.loads(cleaned)
        cities = [RecommendedCity(**c) for c in cities_data[:6]]
        return RecommendCitiesResponse(cities=cities)
    except Exception as e:
        print(f"⚠️ Gemini API failed for recommend_cities: {type(e).__name__}: {e}")
        print(f"   Returning mock response for {request.country}")
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
    # Default city recommendations by country
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
        "thailand": [
            {"name": "Bangkok", "country": "Thailand", "reason": "Vibrant street food, temples, and shopping — great starting point", "lat": 13.7563, "lon": 100.5018},
            {"name": "Phuket", "country": "Thailand", "reason": "Beach paradise with nightlife and water sports", "lat": 7.8804, "lon": 98.3923},
            {"name": "Chiang Mai", "country": "Thailand", "reason": "Cultural heart with temples, mountains, and affordable living", "lat": 18.7883, "lon": 98.9853},
        ],
    }
    
    key = country.lower()
    
    # Check if this looks like preferences rather than a country (contains keywords like beach, cafe, food, etc.)
    preference_keywords = ['beach', 'cafe', 'food', 'mountain', 'culture', 'history', 'adventure', 'relax', 'party', 'shopping']
    is_preference = any(keyword in key for keyword in preference_keywords)
    
    if is_preference:
        # Return diverse popular destinations for preference-based searches
        return RecommendCitiesResponse(cities=[
            RecommendedCity(name="Bali", country="Indonesia", reason="Perfect mix of beaches, culture, and affordability for Indian travelers", lat=-8.4095, lon=115.1889),
            RecommendedCity(name="Phuket", country="Thailand", reason="Beach paradise with great food scene and easy visa access", lat=7.8804, lon=98.3923),
            RecommendedCity(name="Dubai", country="UAE", reason="Luxury shopping and dining with direct flights from India", lat=25.2048, lon=55.2708),
            RecommendedCity(name="Barcelona", country="Spain", reason="Mediterranean beaches, architecture, and vibrant cafe culture", lat=41.3851, lon=2.1734),
            RecommendedCity(name="Prague", country="Czech Republic", reason="Charming cafes, historic sites, and budget-friendly for longer stays", lat=50.0755, lon=14.4378),
        ])
    
    # Return country-specific or generic fallback
    cities_data = defaults.get(key, [
        {"name": f"Capital of {country}", "country": country, "reason": "Primary city with best connectivity from India", "lat": 0.0, "lon": 0.0},
        {"name": f"Second city of {country}", "country": country, "reason": "Cultural hub with rich history", "lat": 0.0, "lon": 0.0},
    ])
    
    return RecommendCitiesResponse(cities=[RecommendedCity(**c) for c in cities_data])
    ])
    return RecommendCitiesResponse(cities=[RecommendedCity(**c) for c in cities_data])
