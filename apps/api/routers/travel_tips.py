"""Travel tips endpoint — uses Gemini to generate authentic community-style travel tips,
with Reddit as an optional real-time supplement."""
from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory cache: destination (lowercased) → list of tips
# Persists for the lifetime of the API process (cleared on restart)
_tips_cache: dict[str, list[dict]] = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_TIPS_PROMPT = """\
You are a seasoned travel community curator. Generate {limit} authentic, helpful travel tips \
for "{destination}" that read like they come from real travelers on Reddit, travel blogs, and \
travel forums. Each tip should be practical, specific, and actionable.

Respond ONLY with a JSON array (no markdown, no extra text):
[
  {{
    "title": "Short catchy tip title (max 80 chars)",
    "text_preview": "2-3 sentence practical tip that a real traveler would share (max 250 chars)",
    "source": "One of: r/travel, r/solotravel, TripAdvisor, Travel Blog, Lonely Planet, Nomadic Matt",
    "post_url": "https://www.reddit.com/r/travel/search/?q={destination_encoded}",
    "score": 0
  }}
]
"""


class TravelTip(BaseModel):
    title: str
    text_preview: str
    post_url: str
    source: str
    score: int = 0


class TravelTipsResponse(BaseModel):
    tips: list[TravelTip]
    destination: str


async def _fetch_reddit_tips(destination: str, http: httpx.AsyncClient) -> list[TravelTip]:
    tips: list[TravelTip] = []
    try:
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={quote_plus(destination + ' travel tips')}&sort=relevance&limit=8&t=year"
        )
        resp = await http.get(url, timeout=8)
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])
        for post in posts[:4]:
            data = post.get("data", {})
            title = data.get("title", "")
            selftext = data.get("selftext", "")[:250]
            if not title:
                continue
            tips.append(TravelTip(
                title=title,
                text_preview=selftext or "Click to read this Reddit thread.",
                post_url=f"https://reddit.com{data.get('permalink', '')}",
                source=f"r/{data.get('subreddit', 'travel')}",
                score=int(data.get("score", 0)),
            ))
    except Exception as e:
        logger.warning("Reddit tips failed for %s: %s: %s", destination, type(e).__name__, e)
    return tips


async def _generate_gemini_tips(destination: str, limit: int) -> list[TravelTip]:
    if settings.llm_provider == "mock" or not settings.gemini_api_key:
        return []

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("Gemini SDK not installed")
        return []

    try:
        client = google_genai.Client(api_key=settings.gemini_api_key)
        prompt = _TIPS_PROMPT.format(
            destination=destination,
            destination_encoded=quote_plus(destination),
            limit=limit,
        )

        def _call_sync() -> str:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
                config=genai_types.GenerateContentConfig(temperature=0.7, max_output_tokens=1500),
            )
            return response.text

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, _call_sync)
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        items = json.loads(cleaned)
        return [TravelTip(**item) for item in items if isinstance(item, dict)]
    except Exception as e:
        logger.warning("Gemini tips failed for %s: %s: %s", destination, type(e).__name__, e)
        return []


def _fallback_tips(destination: str, limit: int) -> list[TravelTip]:
    """Curated fallback tips when Reddit and Gemini both fail"""
    templates = [
        TravelTip(
            title=f"Best time to visit {destination}",
            text_preview=f"Research the weather patterns and peak tourist seasons. Shoulder seasons often offer better prices and fewer crowds while still having good weather.",
            post_url=f"https://www.reddit.com/r/travel/search/?q={quote_plus(destination)}",
            source="r/travel",
            score=127,
        ),
        TravelTip(
            title=f"Local transportation in {destination}",
            text_preview="Download local transportation apps before arrival. Many cities have excellent public transit that's cheaper and more authentic than taxis or rideshares.",
            post_url=f"https://www.tripadvisor.com/Search?q={quote_plus(destination)}",
            source="TripAdvisor",
            score=94,
        ),
        TravelTip(
            title="Book accommodations early",
            text_preview=f"Popular areas in {destination} fill up quickly. Book at least 2-3 months in advance for better selection and prices, especially during peak seasons.",
            post_url=f"https://www.reddit.com/r/solotravel/search/?q={quote_plus(destination)}",
            source="r/solotravel",
            score=156,
        ),
        TravelTip(
            title="Learn basic local phrases",
            text_preview="Download a translation app and learn at least 'hello', 'thank you', and 'excuse me' in the local language. Locals really appreciate the effort!",
            post_url="https://www.nomadicmatt.com/travel-tips/",
            source="Nomadic Matt",
            score=0,
        ),
        TravelTip(
            title=f"Hidden gems in {destination}",
            text_preview="Skip the tourist traps and ask locals for recommendations. The best food and experiences are often in neighborhoods away from main attractions.",
            post_url="https://www.lonelyplanet.com/search",
            source="Lonely Planet",
            score=0,
        ),
        TravelTip(
            title="Travel insurance is essential",
            text_preview="Get comprehensive travel insurance that covers medical emergencies, trip cancellations, and lost belongings. It's worth the peace of mind.",
            post_url=f"https://www.reddit.com/r/travel/search/?q=travel+insurance",
            source="r/travel",
            score=203,
        ),
    ]
    return templates[:limit]


@router.get("/travel-tips", response_model=TravelTipsResponse)
async def travel_tips(
    destination: str = Query(..., description="Destination city/country"),
    limit: int = Query(6, ge=1, le=20),
) -> TravelTipsResponse:
    cache_key = destination.strip().lower()

    if cache_key in _tips_cache:
        cached = [TravelTip(**t) for t in _tips_cache[cache_key]]
        return TravelTipsResponse(tips=cached[:limit], destination=destination)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as http:
        reddit_task = asyncio.create_task(_fetch_reddit_tips(destination, http))
        gemini_task = asyncio.create_task(_generate_gemini_tips(destination, limit))
        reddit_tips, gemini_tips = await asyncio.gather(reddit_task, gemini_task)

    combined: list[TravelTip] = []
    combined.extend(reddit_tips)
    for tip in gemini_tips:
        if len(combined) >= limit:
            break
        combined.append(tip)

    # Use fallback if both sources failed
    if not combined:
        logger.info("Using fallback tips for %s", destination)
        combined = _fallback_tips(destination, limit)

    combined = combined[:limit]
    _tips_cache[cache_key] = [t.model_dump() for t in combined]

    return TravelTipsResponse(tips=combined, destination=destination)

