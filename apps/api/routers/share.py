"""In-memory trip share store: POST /api/share → slug, GET /api/share/{slug} → data."""

import secrets
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter

router = APIRouter()

# Simple in-memory store (resets on server restart — swap for Redis/DB in production)
_store: dict[str, dict] = {}


class ShareRequest(BaseModel):
    itinerary: dict
    trip_config: dict
    labels: dict = {}
    destination_label: str = ""


class ShareResponse(BaseModel):
    slug: str
    url: str


@router.post("/share", response_model=ShareResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_share(request: Request, body: ShareRequest) -> ShareResponse:
    # 128-bit random token (vs. the previous 32-bit uuid4[:8]) so slugs can't
    # be feasibly brute-forced/enumerated at scale.
    slug = secrets.token_urlsafe(16)
    _store[slug] = {
        "itinerary": body.itinerary,
        "trip_config": body.trip_config,
        "labels": body.labels,
        "destination_label": body.destination_label,
    }
    return ShareResponse(slug=slug, url=f"/t/{slug}")


@router.get("/share/{slug}")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_share(request: Request, slug: str) -> dict:
    data = _store.get(slug)
    if not data:
        raise HTTPException(status_code=404, detail="Trip not found or expired")
    return data
