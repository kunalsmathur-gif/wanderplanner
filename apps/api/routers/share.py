"""In-memory trip share store: POST /api/share → slug, GET /api/share/{slug} → data."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
async def create_share(body: ShareRequest) -> ShareResponse:
    slug = uuid.uuid4().hex[:8]
    _store[slug] = {
        "itinerary": body.itinerary,
        "trip_config": body.trip_config,
        "labels": body.labels,
        "destination_label": body.destination_label,
    }
    return ShareResponse(slug=slug, url=f"/t/{slug}")


@router.get("/share/{slug}")
async def get_share(slug: str) -> dict:
    data = _store.get(slug)
    if not data:
        raise HTTPException(status_code=404, detail="Trip not found or expired")
    return data
