"""Extract trip intent from a URL or free-form text."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from chains.extract_trip_chain import extract_trip_from_text, ExtractedTrip, _fetch_url_text

router = APIRouter()


class ExtractTripRequest(BaseModel):
    input: str  # URL or raw text


@router.post("/extract-trip", response_model=ExtractedTrip)
async def extract_trip(body: ExtractTripRequest) -> ExtractedTrip:
    text = body.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    # If it looks like a URL, fetch its content first
    if text.startswith("http://") or text.startswith("https://"):
        fetched = await _fetch_url_text(text)
        if fetched:
            text = fetched
        # If fetch failed, fall through with the URL itself as text

    return await extract_trip_from_text(text)
