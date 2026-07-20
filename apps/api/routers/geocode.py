from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from models.common import GeocodeResponse
from services.geocode import geocode_city

router = APIRouter()


@router.get("/geocode", response_model=GeocodeResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def geocode(
    request: Request,
    q: str = Query(..., min_length=2),
    countrycodes: str = Query(default=""),
):
    return await geocode_city(q, countrycodes=countrycodes)
