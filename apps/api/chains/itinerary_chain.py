from __future__ import annotations
import json
import uuid

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from core.config import settings
from models.itinerary import ItineraryResponse, ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import TripConfig
from services.search import retrieve_context
from chains.scoring import calculate_alignment_score
from chains.safety import apply_kid_safety_filter, inject_persona_modules

SYSTEM_PROMPT = """\
You are WanderPlan, an expert AI travel advisor.
Generate a detailed, realistic day-by-day travel itinerary based on the trip
configuration and destination research provided.

RULES:
- Output ONLY valid JSON matching the schema below. No prose, no markdown.
- Each day must have 3-6 activity items with realistic time allocations.
- Pace guide: relaxed=3-4 items/day, moderate=4-5, packed=5-6.
- Total activity costs must not exceed the stated budget.
- If kids are present: exclude bars, nightclubs, and extreme sports venues.
- If persona includes digital_nomad: add one 2-hour Work Block per day at a wifi cafe or coworking space.
- If persona includes sports_fitness: add one Training Window per day at a gym, trail or sports venue.
- If persona includes pet_parent: only include dog_friendly venues.
- Tag photogenic/scenic spots with "instaworthy" in the tags array.
- Flag schedule conflicts (< 30 min transit gap) in transit_warnings.

OUTPUT SCHEMA:
{{
  "days": [
    {{
      "day_number": 1,
      "date": "YYYY-MM-DD",
      "theme": "string",
      "items": [
        {{
          "id": "unique_string",
          "time_start": "HH:MM",
          "time_end": "HH:MM",
          "title": "string",
          "description": "string",
          "location": {{"lat": 0.0, "lon": 0.0, "address": "string"}},
          "tags": ["string"],
          "booking_url": "string",
          "youtube_video_id": ""
        }}
      ],
      "transit_warnings": []
    }}
  ]
}}

DESTINATION RESEARCH:
{context}

TRIP CONFIGURATION:
{trip_config}
"""


def _build_llm():
    if settings.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=settings.groq_api_key,
            model="llama-3.1-70b-versatile",
            temperature=0.4,
        )
    if settings.llm_provider == "ollama":
        from langchain_community.llms import Ollama
        return Ollama(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


_parser = JsonOutputParser()


async def generate_itinerary(trip_config: TripConfig) -> ItineraryResponse:
    context_docs = await retrieve_context(trip_config)
    context_text = "\n\n".join(doc["text"] for doc in context_docs[:20])

    trip_json = trip_config.model_dump_json(indent=2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
    ])
    llm = _build_llm()
    chain = prompt | llm | _parser

    raw: dict = await chain.ainvoke({
        "context": context_text,
        "trip_config": trip_json,
    })

    days = _parse_days(raw.get("days", []))
    days = apply_kid_safety_filter(days, trip_config)
    days = inject_persona_modules(days, trip_config)

    scored_days = []
    for day in days:
        scored_items = []
        for item in day.items:
            item.alignment_score = calculate_alignment_score(item, trip_config)
            scored_items.append(item)
        day.items = scored_items
        scored_days.append(day)

    overall_score = (
        sum(i.alignment_score for d in scored_days for i in d.items)
        / max(sum(len(d.items) for d in scored_days), 1)
    )

    return ItineraryResponse(days=scored_days, alignment_score=round(overall_score, 2))


def _parse_days(raw_days: list[dict]) -> list[ItineraryDay]:
    days = []
    for rd in raw_days:
        items = []
        for ri in rd.get("items", []):
            loc = ri.get("location", {})
            items.append(ItineraryItem(
                id=ri.get("id") or str(uuid.uuid4()),
                time_start=ri.get("time_start", "09:00"),
                time_end=ri.get("time_end", "10:00"),
                title=ri.get("title", ""),
                description=ri.get("description", ""),
                location=ItineraryItemLocation(
                    lat=loc.get("lat", 0.0),
                    lon=loc.get("lon", 0.0),
                    address=loc.get("address", ""),
                ),
                tags=ri.get("tags", []),
                booking_url=ri.get("booking_url", ""),
                youtube_video_id=ri.get("youtube_video_id", ""),
            ))
        days.append(ItineraryDay(
            day_number=rd.get("day_number", 1),
            date=rd.get("date", ""),
            theme=rd.get("theme", ""),
            items=items,
        ))
    return days
