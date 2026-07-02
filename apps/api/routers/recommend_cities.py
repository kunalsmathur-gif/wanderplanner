
from fastapi import APIRouter, HTTPException, Request
from chains.recommend_cities_chain import RecommendCitiesRequest, RecommendCitiesResponse, recommend_cities
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/recommend-cities", response_model=RecommendCitiesResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def recommend_cities_endpoint(request: Request, body: RecommendCitiesRequest) -> RecommendCitiesResponse:
    try:
        return await recommend_cities(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="recommend-cities"))
