"""Feasibility chain — uses Gemini to estimate trip costs and check budget."""
from __future__ import annotations

import asyncio
import json

from core.config import settings
from core.prompt_guard import neutralize
from models.feasibility import FeasibilityResponse, CostBreakdown, AlternativeDestination
from models.trip import TripConfig

FEASIBILITY_PROMPT = """\
You are a travel cost expert. Estimate the realistic total cost (in Indian Rupees) for the
trip described below for travelers departing from India.

Provide cost estimates based on average market rates. Be conservative (lean slightly higher).

TRIP DETAILS:
{trip_config}

OUTPUT SCHEMA (valid JSON only, no markdown):
{{
  "flights_inr": <round-trip economy flight cost per person × total passengers>,
  "visa_inr": <total visa fees for all passengers, 0 if visa-free for Indians>,
  "accommodation_inr": <avg nightly rate in INR × number of nights × number of rooms needed>,
  "daily_expenses_inr": <food + activities + local transport per person per day × days × people>,
  "total_estimated_inr": <sum of all above>,
  "alternatives": [
    {{
      "city": "string",
      "country": "string",
      "estimated_total_inr": <integer>,
      "why_cheaper": "short reason e.g. No visa required, budget flights available",
      "similar_experiences": ["experience1", "experience2"]
    }}
  ]
}}

RULES:
- Convert all costs to INR.
- Use average economy class fares from major Indian airports.
- For accommodation, use the style specified (hostel/budget/boutique/luxury).
- If budget is clearly insufficient, suggest 2-3 cheaper alternatives that offer similar experiences.
- If budget is sufficient, still suggest 1-2 alternative destinations for variety.
- Keep alternatives realistic for Indian passport holders.
- Return ONLY valid JSON matching the schema above.
"""


async def check_feasibility(trip_config: TripConfig) -> FeasibilityResponse:
    """Call Gemini to estimate trip costs and check budget feasibility."""

    # Calculate total people
    group = trip_config.group if isinstance(trip_config.group, dict) else trip_config.group.__dict__
    if hasattr(trip_config.group, 'adults'):
        adults = trip_config.group.adults
        seniors = trip_config.group.seniors
        kids = len(trip_config.group.kids) if trip_config.group.kids else 0
    else:
        adults = group.get('adults', 1)
        seniors = group.get('seniors', 0)
        kids = len(group.get('kids', []))
    total_people = adults + seniors + kids

    # Calculate trip nights
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else trip_config.dates.__dict__
    if hasattr(trip_config.dates, 'start'):
        start = trip_config.dates.start
        end = trip_config.dates.end
    else:
        start = dates.get('start') or dates.get('start_date')
        end = dates.get('end') or dates.get('end_date')

    nights = 4  # default
    if start and end:
        try:
            from datetime import date
            nights = max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days)
        except Exception:
            pass

    dest = trip_config.destination.city if trip_config.destination else "the destination"
    budget_inr = int(trip_config.budget.amount)

    trip_summary = {
        "destination": dest,
        "origin": trip_config.origin.city,
        "nights": nights,
        "total_people": total_people,
        "adults": adults,
        "kids_count": kids,
        "seniors": seniors,
        "accommodation_style": trip_config.accommodation.style[0] if trip_config.accommodation.style else "mid-range hotel",
        "budget_inr": budget_inr,
        "purpose": trip_config.purpose,
    }

    if settings.llm_provider == "mock":
        return _mock_feasibility(trip_summary, budget_inr)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    prompt = FEASIBILITY_PROMPT.format(
        trip_config=neutralize(json.dumps(trip_summary, indent=2), context="trip summary")
    )

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        return response.text

    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _call_sync)

    # Parse response
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])

    data = json.loads(cleaned)
    return _build_response(data, budget_inr)


def _build_response(data: dict, budget_inr: int) -> FeasibilityResponse:
    total = int(data.get("total_estimated_inr", 0))
    feasible = total <= budget_inr

    breakdown = CostBreakdown(
        flights_inr=int(data.get("flights_inr", 0)),
        visa_inr=int(data.get("visa_inr", 0)),
        accommodation_inr=int(data.get("accommodation_inr", 0)),
        daily_expenses_inr=int(data.get("daily_expenses_inr", 0)),
        total_estimated_inr=total,
    )

    alternatives = [
        AlternativeDestination(
            city=a.get("city", ""),
            country=a.get("country", ""),
            estimated_total_inr=int(a.get("estimated_total_inr", 0)),
            why_cheaper=a.get("why_cheaper", ""),
            similar_experiences=a.get("similar_experiences", []),
        )
        for a in data.get("alternatives", [])
    ]

    if feasible:
        verdict = f"✅ Budget looks sufficient! Estimated trip cost is ₹{total:,}."
        buffer = budget_inr - total
        shortfall = 0
    else:
        shortfall = total - budget_inr
        buffer = 0
        verdict = f"⚠️ Budget may be short by ₹{shortfall:,}. Estimated minimum is ₹{total:,}."

    return FeasibilityResponse(
        feasible=feasible,
        verdict=verdict,
        budget_inr=budget_inr,
        breakdown=breakdown,
        shortfall_inr=shortfall,
        buffer_inr=buffer,
        alternatives=alternatives,
    )


def _mock_feasibility(trip_summary: dict, budget_inr: int) -> FeasibilityResponse:
    """Mock response for dev mode."""
    nights = trip_summary.get("nights", 4)
    people = trip_summary.get("total_people", 2)
    dest = trip_summary.get("destination", "Tokyo")

    flights = 35000 * people
    visa = 6500 * people
    accommodation = 4500 * nights
    daily = 3000 * nights * people
    total = flights + visa + accommodation + daily

    alternatives = [
        AlternativeDestination(
            city="Bali",
            country="Indonesia",
            estimated_total_inr=int(total * 0.6),
            why_cheaper="No visa required for Indians, budget flights from major cities",
            similar_experiences=["Beaches", "Temples", "Nightlife"],
        ),
        AlternativeDestination(
            city="Bangkok",
            country="Thailand",
            estimated_total_inr=int(total * 0.55),
            why_cheaper="Visa-on-arrival, affordable street food and stays",
            similar_experiences=["Street food", "Temples", "Shopping"],
        ),
    ]

    return _build_response(
        {
            "flights_inr": flights,
            "visa_inr": visa,
            "accommodation_inr": accommodation,
            "daily_expenses_inr": daily,
            "total_estimated_inr": total,
            "alternatives": [a.model_dump() for a in alternatives],
        },
        budget_inr,
    )
