"""Extract trip intent from a URL or free-form text."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from chains.extract_trip_chain import extract_trip_from_text, ExtractedTrip, fetch_url_text
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


class ExtractTripRequest(BaseModel):
    input: str  # URL or raw text


@router.post("/extract-trip", response_model=ExtractedTrip)
@limiter.limit(LLM_RATE_LIMIT)
async def extract_trip(request: Request, body: ExtractTripRequest) -> ExtractedTrip:
    text = body.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    # If it looks like a URL, fetch its content first
    if text.startswith("http://") or text.startswith("https://"):
        fetched = await fetch_url_text(text)
        if fetched:
            text = fetched
        # If fetch failed, fall through with the URL itself as text

    return await extract_trip_from_text(text)
