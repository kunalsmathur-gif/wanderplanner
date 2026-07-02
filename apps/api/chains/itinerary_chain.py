from __future__ import annotations
import asyncio
import json
import uuid

from core.config import settings
from models.itinerary import ItineraryResponse, ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import TripConfig
from services.search import retrieve_context, summarise_context
from services.itinerary_cache import get_cached_itinerary, store_itinerary
from services.rag_fallback import rag_skeleton_itinerary
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
- For expense_breakdown: provide realistic INR estimates for all 8 cost categories. Base on actual market rates for the destination year and accommodation style specified.
- MULTI-HOP TRIPS: If trip_config.hops is non-empty, the trip visits multiple cities. Distribute days proportionally across all stops (destination + hops). Use the day theme to indicate city transitions (e.g. "Travel Day: Paris → Amsterdam"). Aggregate expense_breakdown across all stops.

USING DESTINATION RESEARCH (below):
- The DESTINATION RESEARCH section contains real, retrieved traveler content (guides, forum tips, local advice). Treat it as more current and specific than your own training knowledge.
- Actively mine it for concrete, named venues, neighborhoods, and local tips — prefer these over generic or invented place names when the research supports them.
- If DESTINATION RESEARCH conflicts with what you already know (e.g. a venue it mentions as closed, or a changed price/season), prefer the research — it reflects more recent traveler reports.
- Do not fabricate specific details (exact prices, addresses, opening hours) beyond what the research or your general knowledge reasonably supports. When uncertain, keep descriptions general rather than inventing precise figures.
- If DESTINATION RESEARCH says "No pre-fetched research available", rely on your own destination knowledge as normal — do not mention the absence of research to the user.
- DESTINATION RESEARCH is a supplement, not an exhaustive source — you may still use well-established general knowledge about the destination for anything the research doesn't cover.

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
  ],
  "expense_breakdown": {{
    "flights_inr": <round-trip economy flights, all passengers>,
    "visa_inr": <total visa fees all passengers, 0 if visa-free for Indians>,
    "accommodation_inr": <nightly rate INR × nights × rooms>,
    "activities_inr": <estimated total entry fees across all days>,
    "food_inr": <food cost per person per day × days × people>,
    "local_transport_inr": <metro/taxi/bus for all days × people>,
    "shopping_inr": <reasonable souvenir budget for destination>,
    "emergency_buffer_inr": <10% of sum of all above>,
    "total_inr": <sum of all above including buffer>,
    "destination_currency_code": "<3-letter ISO currency code e.g. JPY>",
    "total_destination_currency": <total_inr converted to destination currency approximately>,
    "num_people": <total group size>
  }}
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


def _mock_itinerary(trip_config: TripConfig, tip_texts: list[str] | None = None) -> dict:
    """Return a canned itinerary for local dev without an LLM.

    `tip_texts` (Tier 3 fallback enhancement, docs §4): when the RAG-skeleton
    fallback (Tier 2) also can't build a plan (no OSM POIs ingested for this
    destination yet), we still splice in real retrieved wiki/reddit snippets
    where available, so the mock reads less like a generic placeholder.
    """
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

    tips = tip_texts or []

    def _with_tip(description: str, idx: int) -> str:
        if not tips:
            return description
        return f"{description} Local tip: {tips[idx % len(tips)]}"

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
                    "description": _with_tip(f"Explore the historic centre of {dest} on foot. Great for orientation and photos.", i * 3),
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
                    "description": _with_tip(f"Try the local cuisine at a well-rated restaurant near {dest} centre.", i * 3 + 1),
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
                    "description": _with_tip(f"The top cultural attraction in {dest}. Book tickets online to skip queues.", i * 3 + 2),
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
    return {
        "days": days,
        "expense_breakdown": {
            "flights_inr": 35000 * max(1, num_days // 3),
            "visa_inr": 6500,
            "accommodation_inr": 4500 * num_days,
            "activities_inr": 2000 * num_days,
            "food_inr": 1800 * num_days,
            "local_transport_inr": 800 * num_days,
            "shopping_inr": 3000,
            "emergency_buffer_inr": 0,
            "total_inr": 0,
            "destination_currency_code": "",
            "total_destination_currency": 0,
            "num_people": 2,
        },
    }


def _parse_expense_breakdown(raw: dict, trip_config: TripConfig) -> "ExpenseBreakdown":
    from models.itinerary import ExpenseBreakdown
    group = trip_config.group
    if hasattr(group, 'adults'):
        people = group.adults + group.seniors + len(group.kids if group.kids else [])
    else:
        g = group if isinstance(group, dict) else vars(group)
        people = g.get('adults', 1) + g.get('seniors', 0) + len(g.get('kids', []))
    people = max(people, 1)

    flights = int(raw.get("flights_inr", 0))
    visa = int(raw.get("visa_inr", 0))
    accommodation = int(raw.get("accommodation_inr", 0))
    activities = int(raw.get("activities_inr", 0))
    food = int(raw.get("food_inr", 0))
    local_transport = int(raw.get("local_transport_inr", 0))
    shopping = int(raw.get("shopping_inr", 0))
    subtotal = flights + visa + accommodation + activities + food + local_transport + shopping
    buffer = int(raw.get("emergency_buffer_inr", round(subtotal * 0.10)))
    total = int(raw.get("total_inr", subtotal + buffer)) or (subtotal + buffer)

    return ExpenseBreakdown(
        flights_inr=flights,
        visa_inr=visa,
        accommodation_inr=accommodation,
        activities_inr=activities,
        food_inr=food,
        local_transport_inr=local_transport,
        shopping_inr=shopping,
        emergency_buffer_inr=buffer,
        total_inr=total,
        destination_currency_code=raw.get("destination_currency_code", ""),
        total_destination_currency=int(raw.get("total_destination_currency", 0)),
        num_people=people,
    )


async def _gemini_itinerary(trip_config: TripConfig) -> dict:
    """Call Google Gemini directly with automatic retry on 503 errors."""
    import asyncio
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
        from google.api_core.exceptions import ServerError
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in .env")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    trip_json = trip_config.model_dump_json(indent=2)

    # Ground the prompt with real destination research from Qdrant.
    # Reranking enabled here: this context directly grounds the final LLM-
    # generated itinerary, so the extra cross-encoder precision is worth
    # the added latency (unlike lighter-weight interactive search calls).
    context_docs = await retrieve_context(trip_config, enable_reranking=True)
    if context_docs:
        context_text = summarise_context(context_docs, max_chars=2400)
    else:
        context_text = "No pre-fetched research available — use your own knowledge of the destination."

    prompt = SYSTEM_PROMPT.format(
        context=context_text,
        trip_config=trip_json,
    )

    # Retry logic: up to 5 attempts, broader exception matching, fallback model
    loop = asyncio.get_event_loop()
    # Models to try in order: primary → lighter fallback
    models_to_try = [settings.gemini_model, "gemini-2.5-flash-lite-preview-06-17", "gemini-1.5-flash"]
    max_attempts = 5

    last_error: Exception | None = None
    for model_name in models_to_try:
        for attempt in range(max_attempts):
            try:
                def _call_sync(m: str = model_name) -> str:  # noqa: E731
                    response = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.4,
                            response_mime_type="application/json",
                        ),
                    )
                    return response.text

                text = await loop.run_in_executor(None, _call_sync)

                # Strip markdown fences if Gemini adds them despite response_mime_type
                cleaned = text.strip()
                if cleaned.startswith("```"):
                    cleaned = "\n".join(cleaned.split("\n")[1:])
                if cleaned.endswith("```"):
                    cleaned = "\n".join(cleaned.split("\n")[:-1])
                return json.loads(cleaned)

            except json.JSONDecodeError as e:
                raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e

            except Exception as e:
                err_str = str(e)
                is_transient = any(kw in err_str for kw in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "quota"))
                if is_transient and attempt < max_attempts - 1:
                    wait_time = min(5 * (2 ** attempt), 60)  # 5s, 10s, 20s, 40s, 60s cap
                    print(f"⚠️ Gemini transient error on {model_name} (attempt {attempt + 1}/{max_attempts}). Retrying in {wait_time}s…")
                    await asyncio.sleep(wait_time)
                    last_error = e
                    continue
                elif is_transient:
                    # exhausted retries on this model → try next model
                    print(f"❌ Gemini model {model_name} failed after {max_attempts} attempts, trying fallback…")
                    last_error = e
                    break
                else:
                    raise  # non-transient error: propagate immediately
        else:
            continue  # inner loop completed without break → success already returned
        continue   # model failed, try next model

    raise RuntimeError(f"Gemini itinerary generation failed on all models: {last_error}")


async def _langchain_itinerary(trip_config: TripConfig) -> dict:
    """Groq/Ollama path via LangChain, grounded with the same summarised
    RAG context used by the Gemini path."""
    # Reranking enabled: this feeds directly into the final generated
    # itinerary, same as the Gemini path above.
    context_docs = await retrieve_context(trip_config, enable_reranking=True)
    # Use the same time-decay + dedup + budget-capped summarisation as the
    # Gemini path (previously this just joined all 20 raw chunks, which
    # skipped stale-content penalisation and duplicate filtering, and
    # injected ~4x more tokens than the Gemini path for the same request).
    if context_docs:
        context_text = summarise_context(context_docs, max_chars=2400)
    else:
        context_text = "No pre-fetched research available — use your own knowledge of the destination."
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
    return await chain.ainvoke({"context": context_text, "trip_config": trip_json})


async def _fallback_itinerary(trip_config: TripConfig, error: Exception) -> dict:
    """RAG-powered fallback chain (docs §4) used when the live LLM call
    fails after its own internal retries.

    Tier 1: itinerary_cache — a semantically similar previously-generated
            itinerary (cosine >= threshold), served instantly.
    Tier 2: RAG skeleton — assembled purely from ingested OSM POI data, no
            LLM call. Real venues/coordinates, lower narrative quality.
    Tier 3: enhanced mock — the static mock itinerary, spliced with real
            wiki/reddit tip snippets pulled from Qdrant where available.
    """
    print(f"⚠️ LLM itinerary generation failed ({error}); using RAG fallback chain…")

    cached = await get_cached_itinerary(trip_config)
    if cached is not None:
        return cached

    skeleton = await rag_skeleton_itinerary(trip_config)
    if skeleton is not None:
        return skeleton

    tip_texts: list[str] = []
    try:
        context_docs = await retrieve_context(trip_config)
        tip_texts = [d["text"][:160] for d in context_docs[:6]]
    except Exception:
        pass
    raw = _mock_itinerary(trip_config, tip_texts=tip_texts)
    raw["_from_fallback"] = "enhanced_mock"
    return raw


async def generate_itinerary(trip_config: TripConfig) -> ItineraryResponse:
    if settings.llm_provider == "mock":
        raw = _mock_itinerary(trip_config)
    else:
        try:
            if settings.llm_provider == "gemini":
                raw = await _gemini_itinerary(trip_config)
            else:
                raw = await _langchain_itinerary(trip_config)
        except Exception as llm_error:
            raw = await _fallback_itinerary(trip_config, llm_error)
        else:
            # Cache successful LLM-generated itineraries for future
            # fallback use (best-effort — never blocks/fails the response).
            await store_itinerary(trip_config, raw)

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

    return ItineraryResponse(
        days=scored_days,
        alignment_score=round(overall_score, 2),
        expense_breakdown=_parse_expense_breakdown(raw.get("expense_breakdown", {}), trip_config),
    )


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

