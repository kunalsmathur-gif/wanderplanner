"""Trip share store: POST /api/share → slug, GET /api/share/{slug} → data.

Backed by Redis in production (persists across restarts/deploys, shared
across instances) with an in-process dict fallback for local dev — see
core/redis_client.py. Links expire after `settings.share_link_ttl_seconds`
(90 days by default) rather than living forever.
"""

import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.redis_client import get_cache

router = APIRouter()


class ShareRequest(BaseModel):
    itinerary: dict
    trip_config: dict
    labels: dict = {}
    destination_label: str = ""


class ShareResponse(BaseModel):
    slug: str
    url: str


def _share_key(slug: str) -> str:
    return f"share:{slug}"


@router.post("/share", response_model=ShareResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_share(request: Request, body: ShareRequest) -> ShareResponse:
    # 128-bit random token (vs. the previous 32-bit uuid4[:8]) so slugs can't
    # be feasibly brute-forced/enumerated at scale.
    slug = secrets.token_urlsafe(16)
    await get_cache().set_json(
        _share_key(slug),
        {
            "itinerary": body.itinerary,
            "trip_config": body.trip_config,
            "labels": body.labels,
            "destination_label": body.destination_label,
        },
        ttl_seconds=settings.share_link_ttl_seconds,
    )
    return ShareResponse(slug=slug, url=f"/t/{slug}")


@router.get("/share/{slug}")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_share(request: Request, slug: str) -> dict:
    data = await get_cache().get_json(_share_key(slug))
    # The cache Protocol returns `object | None` on purpose — it round-trips
    # arbitrary JSON — so the shape is narrowed here rather than widened
    # there. Doubles as a guard against a malformed or legacy cache entry.
    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=404, detail="Trip not found or expired")
    return data

