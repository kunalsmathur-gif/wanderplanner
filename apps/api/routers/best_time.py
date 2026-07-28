from __future__ import annotations

from fastapi import APIRouter, Path, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.validation import MAX_CITY_LEN, validate_query_param
from models.common import BestTimeResponse
from services.best_time import get_best_time

router = APIRouter()


@router.get("/best-time/{destination}", response_model=BestTimeResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def best_time(
    request: Request,
    destination: str = Path(..., min_length=1, max_length=MAX_CITY_LEN),
):
    destination = validate_query_param(
        destination, field="destination", max_length=MAX_CITY_LEN, require_alphanumeric=True
    )
    return await get_best_time(destination)
