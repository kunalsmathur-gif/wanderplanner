from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from models.common import SearchResponse
from services.search import semantic_search

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def search(
    request: Request,
    q: str = Query(..., min_length=2),
    destination: str = Query(...),
    limit: int = Query(default=10, ge=1, le=30),
):
    results = await semantic_search(q, destination, limit)
    return SearchResponse(results=results)
