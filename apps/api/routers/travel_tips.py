"""Travel tips endpoint — real Reddit tips (live search, real permalinks/scores)
supplemented by honestly-labelled LLM-generated general tips.

Provenance rule: only tips fetched from a real community source may carry a
community label (r/…) or a score. LLM and template tips are always labelled
"General tip" with no score and no third-party branding — enforced in code,
not just in the prompt."""
from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.llm_client import track_gemini_usage
from core.llm_usage import reset_usage
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import User

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
You are a knowledgeable travel assistant. Generate {limit} practical, specific, actionable \
travel tips for "{destination}". Do NOT imitate or attribute the tips to any person, website, \
or community — they will be shown to the user labelled as general tips.

Respond ONLY with a JSON array (no markdown, no extra text):
[
  {{
    "title": "Short tip title (max 80 chars)",
    "text_preview": "2-3 sentence practical tip (max 250 chars)"
  }}
]
"""

# Honest label for tips that do not come from a real community source.
GENERAL_TIP_SOURCE = "General tip"


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
        prompt = _TIPS_PROMPT.format(destination=destination, limit=limit)

        def _call_sync():
            return client.models.generate_content(
                model=settings.gemini_model,
                contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
                config=genai_types.GenerateContentConfig(temperature=0.7, max_output_tokens=1500),
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _call_sync)
        track_gemini_usage(response, model=settings.gemini_model, purpose="travel_tips")
        raw = response.text
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        items = json.loads(cleaned)
        # Provenance enforced here: whatever the model returned, LLM tips carry
        # the honest label, no score, and no link masquerading as a source.
        return [
            TravelTip(
                title=str(item.get("title", "")).strip(),
                text_preview=str(item.get("text_preview", "")).strip(),
                post_url="",
                source=GENERAL_TIP_SOURCE,
                score=0,
            )
            for item in items
            if isinstance(item, dict) and item.get("title")
        ]
    except Exception as e:
        logger.warning("Gemini tips failed for %s: %s: %s", destination, type(e).__name__, e)
        return []


def _fallback_tips(destination: str, limit: int) -> list[TravelTip]:
    """Curated template tips when Reddit and Gemini both fail — labelled honestly,
    never with a community source or an invented score."""
    texts = [
        (
            f"Best time to visit {destination}",
            "Research the weather patterns and peak tourist seasons. Shoulder seasons often offer better prices and fewer crowds while still having good weather.",
        ),
        (
            f"Local transportation in {destination}",
            "Download local transportation apps before arrival. Many cities have excellent public transit that's cheaper and more authentic than taxis or rideshares.",
        ),
        (
            "Book accommodations early",
            f"Popular areas in {destination} fill up quickly. Book at least 2-3 months in advance for better selection and prices, especially during peak seasons.",
        ),
        (
            "Learn basic local phrases",
            "Download a translation app and learn at least 'hello', 'thank you', and 'excuse me' in the local language. Locals really appreciate the effort!",
        ),
        (
            f"Hidden gems in {destination}",
            "Skip the tourist traps and ask locals for recommendations. The best food and experiences are often in neighborhoods away from main attractions.",
        ),
        (
            "Travel insurance is essential",
            "Get comprehensive travel insurance that covers medical emergencies, trip cancellations, and lost belongings. It's worth the peace of mind.",
        ),
    ]
    return [
        TravelTip(title=title, text_preview=preview, post_url="", source=GENERAL_TIP_SOURCE, score=0)
        for title, preview in texts[:limit]
    ]


@router.get("/travel-tips", response_model=TravelTipsResponse)
async def travel_tips(
    destination: str = Query(..., description="Destination city/country"),
    limit: int = Query(6, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> TravelTipsResponse:
    reset_usage()
    try:
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
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)

