from __future__ import annotations

from fastapi import APIRouter, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from models.common import BestTimeResponse
from services.best_time import get_best_time

router = APIRouter()


@router.get("/best-time/{destination}", response_model=BestTimeResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def best_time(request: Request, destination: str):
    return await get_best_time(destination)
