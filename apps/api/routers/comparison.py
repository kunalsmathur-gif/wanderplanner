from fastapi import APIRouter, HTTPException, Query, Request
from models.itinerary import CompareDestinationsRequest, ComparisonResponse
from services.comparison import build_comparison
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/compare-destinations", response_model=ComparisonResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def compare_destinations(request: Request, body: CompareDestinationsRequest):
    try:
        return await build_comparison(body.destinations, body.trip_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="compare-destinations"))
