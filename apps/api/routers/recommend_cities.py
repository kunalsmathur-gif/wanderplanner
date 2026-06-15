from __future__ import annotations

from fastapi import APIRouter, HTTPException
from chains.recommend_cities_chain import RecommendCitiesRequest, RecommendCitiesResponse, recommend_cities

router = APIRouter()


@router.post("/recommend-cities", response_model=RecommendCitiesResponse)
async def recommend_cities_endpoint(request: RecommendCitiesRequest) -> RecommendCitiesResponse:
    try:
        return await recommend_cities(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
