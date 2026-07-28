from __future__ import annotations

from fastapi import APIRouter, Query, Request

from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.validation import MAX_CITY_LEN, MAX_SEARCH_QUERY_LEN, validate_query_param
from models.common import SearchResponse
from services.search import semantic_search

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=MAX_SEARCH_QUERY_LEN),
    destination: str = Query(..., max_length=MAX_CITY_LEN),
    limit: int = Query(default=10, ge=1, le=30),
):
    # `q` is embedded (a real model call) and `destination` becomes a Qdrant
    # payload filter, so both are bounded before they get there.
    q = validate_query_param(q, field="q", max_length=MAX_SEARCH_QUERY_LEN)
    destination = validate_query_param(
        destination, field="destination", max_length=MAX_CITY_LEN, require_alphanumeric=True
    )
    results = await semantic_search(q, destination, limit)
    return SearchResponse(results=results)
