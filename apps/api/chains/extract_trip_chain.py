"""Extract trip intent from a URL or free-form text (blog post, Reddit thread, notes)."""
from __future__ import annotations

import asyncio
import json
import re

import httpx
from pydantic import BaseModel

from core.config import settings


class ExtractedTrip(BaseModel):
    destination: str | None = None
    destination_country: str | None = None
    duration_days: int | None = None
    themes: list[str] = []
    budget_inr: int | None = None
    summary: str = ""


_EXTRACT_SYSTEM_PROMPT = """\
You are a travel data extraction assistant. Given a piece of text (from a blog, Reddit, notes or any source), extract structured trip information.

RESPONSE FORMAT — respond ONLY with valid JSON, no markdown fences:
{
  "destination": "City name only (e.g. Bali, Paris). null if not found.",
  "destination_country": "Country name (e.g. Indonesia, France). null if not found.",
  "duration_days": <integer number of days, or null if not mentioned>,
  "themes": ["list", "of", "trip", "themes", "like", "Beach", "Culture", "Food"],
  "budget_inr": <approximate total budget in INR as integer, or null if not mentioned>,
  "summary": "One sentence describing what this trip is about."
}
"""


async def _fetch_url_text(url: str) -> str:
    """Fetch a URL and return plain text (first 6000 chars to stay within token budget)."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "WanderPlan/1.0"})
            resp.raise_for_status()
            text = resp.text
            # Strip HTML tags
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:6000]
    except Exception:
        return ""


async def extract_trip_from_text(text: str) -> ExtractedTrip:
    """Use Gemini to extract trip fields from free-form text."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=_EXTRACT_SYSTEM_PROMPT,
    )

    prompt = f"Extract trip info from the following text:\n\n{text[:4000]}"

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 512},
            )
            raw = response.text.strip()
            # Strip possible markdown fences
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            return ExtractedTrip(**data)
        except Exception:
            if attempt == 2:
                break
            await asyncio.sleep(1)

    return ExtractedTrip(summary="Could not extract trip details from this content.")
