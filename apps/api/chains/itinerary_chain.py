from __future__ import annotations
import json
import uuid

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
- For local_name: provide the place name in local script only when it differs from English (e.g. 浅草寺 for Senso-ji, 에펠탑 for Eiffel Tower). Leave empty for English-named places.
- For youtube_search_query: generate a short, specific search phrase travelers would use (e.g. "Senso-ji Temple Tokyo travel guide").

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
          "local_name": "place name in local script e.g. 浅草寺 (leave empty if same script as English)",
          "description": "string",
          "location": {{"lat": 0.0, "lon": 0.0, "address": "string"}},
          "tags": ["string"],
          "booking_url": "string",
          "youtube_video_id": "",
          "youtube_search_query": "short search phrase for YouTube e.g. Senso-ji Temple Tokyo travel guide"
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
    if settings.llm_provider == "mock":
        return None  # handled in generate_itinerary
    if settings.llm_provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise RuntimeError("langchain-groq not installed. Run: pip install -r requirements-ml.txt")
        return ChatGroq(
            api_key=settings.groq_api_key,
            model="llama-3.1-70b-versatile",
            temperature=0.4,
        )
    if settings.llm_provider == "ollama":
        try:
            from langchain_community.llms import Ollama
        except ImportError:
            raise RuntimeError("langchain-community not installed. Run: pip install -r requirements-ml.txt")
        return Ollama(base_url=settings.ollama_base_url, model=settings.ollama_model)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _mock_itinerary(trip_config: TripConfig) -> dict:
    """Return a canned itinerary for local dev without an LLM."""
    dest = trip_config.destination.city if trip_config.destination else "the destination"
    dates = trip_config.dates if isinstance(trip_config.dates, dict) else {}
    start = dates.get("start_date") or dates.get("start") or "2026-11-14"
    from datetime import date, timedelta
    try:
        base = date.fromisoformat(start)
    except Exception:
        base = date(2026, 11, 14)
    num_days = 3
    end_raw = dates.get("end_date") or dates.get("end")
    if start and end_raw:
        try:
            num_days = max(1, (date.fromisoformat(end_raw) - base).days)
        except Exception:
            pass

    days = []
    themes = ["Arrival & City Highlights", "Culture & Food", "Day Trip & Leisure"]
    for i in range(num_days):
        day_date = (base + timedelta(days=i)).isoformat()
        theme = themes[i % len(themes)]
        days.append({
            "day_number": i + 1,
            "date": day_date,
            "theme": theme,
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "09:00",
                    "time_end": "11:00",
                    "title": f"Morning Walk — {dest} Old Town",
                    "description": f"Explore the historic centre of {dest} on foot. Great for orientation and photos.",
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"Old Town, {dest}"},
                    "tags": ["instaworthy"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "12:00",
                    "time_end": "13:30",
                    "title": "Local Lunch",
                    "description": f"Try the local cuisine at a well-rated restaurant near {dest} centre.",
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"City Centre, {dest}"},
                    "tags": ["kid_friendly"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
                {
                    "id": str(uuid.uuid4()),
                    "time_start": "15:00",
                    "time_end": "18:00",
                    "title": f"{dest} Main Museum",
                    "description": f"The top cultural attraction in {dest}. Book tickets online to skip queues.",
                    "location": {"lat": 0.0, "lon": 0.0, "address": f"Museum District, {dest}"},
                    "tags": ["kid_friendly", "instaworthy"],
                    "local_name": "",
                    "booking_url": "",
                    "youtube_video_id": "",
                    "youtube_search_query": "",
                },
            ],
            "transit_warnings": [],
        })
    return {"days": days}


async def _gemini_itinerary(trip_config: TripConfig) -> dict:
    """Call Google Gemini directly — no langchain, no sentence-transformers needed."""
    import asyncio
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    trip_json = trip_config.model_dump_json(indent=2)

    prompt = SYSTEM_PROMPT.format(
        context="No pre-fetched research available — use your own knowledge of the destination.",
        trip_config=trip_json,
    )

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
        return response.text

    # Run blocking SDK call in thread pool so the event loop stays free
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _call_sync)

    try:
        # Strip markdown fences if Gemini adds them despite response_mime_type
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.split("\n")[:-1])
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e


async def generate_itinerary(trip_config: TripConfig) -> ItineraryResponse:
    if settings.llm_provider == "mock":
        raw = _mock_itinerary(trip_config)
    elif settings.llm_provider == "gemini":
        raw = await _gemini_itinerary(trip_config)
    else:
        context_docs = await retrieve_context(trip_config)
        context_text = "\n\n".join(doc["text"] for doc in context_docs[:20])
        trip_json = trip_config.model_dump_json(indent=2)
        try:
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.output_parsers import JsonOutputParser
        except ImportError:
            raise RuntimeError("langchain not installed. Run: pip install -r requirements-ml.txt")

        prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT)])
        llm = _build_llm()
        parser = JsonOutputParser()
        chain = prompt | llm | parser
        raw = await chain.ainvoke({"context": context_text, "trip_config": trip_json})

    days = _parse_days(raw.get("days", []))
    days = apply_kid_safety_filter(days, trip_config)
    days = inject_persona_modules(days, trip_config)

    scored_days = []
    for day in days:
        scored_items = [
            item.model_copy(update={"alignment_score": calculate_alignment_score(item, trip_config)})
            for item in day.items
        ]
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
                local_name=ri.get("local_name", ""),
                tags=ri.get("tags", []),
                booking_url=ri.get("booking_url", ""),
                youtube_video_id=ri.get("youtube_video_id", ""),
                youtube_search_query=ri.get("youtube_search_query", ""),
            ))
        days.append(ItineraryDay(
            day_number=rd.get("day_number", 1),
            date=rd.get("date", ""),
            theme=rd.get("theme", ""),
            items=items,
        ))
    return days


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
- For local_name: provide the place name in local script only when it differs from English (e.g. 浅草寺 for Senso-ji, 에펠탑 for Eiffel Tower). Leave empty for English-named places.
- For youtube_search_query: generate a short, specific search phrase travelers would use (e.g. "Senso-ji Temple Tokyo travel guide").

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
          "local_name": "place name in local script e.g. 浅草寺 (leave empty if same script as English)",
          "description": "string",
          "location": {{"lat": 0.0, "lon": 0.0, "address": "string"}},
          "tags": ["string"],
          "booking_url": "string",
          "youtube_video_id": "",
          "youtube_search_query": "short search phrase for YouTube e.g. Senso-ji Temple Tokyo travel guide"
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
                local_name=ri.get("local_name", ""),
                tags=ri.get("tags", []),
                booking_url=ri.get("booking_url", ""),
                youtube_video_id=ri.get("youtube_video_id", ""),
                youtube_search_query=ri.get("youtube_search_query", ""),
            ))
        days.append(ItineraryDay(
            day_number=rd.get("day_number", 1),
            date=rd.get("date", ""),
            theme=rd.get("theme", ""),
            items=items,
        ))
    return days
