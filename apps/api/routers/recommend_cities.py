

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chains.recommend_cities_chain import (
    RecommendCitiesRequest,
    RecommendCitiesResponse,
    recommend_cities,
)
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from core.errors import sanitize_error
from core.llm_usage import reset_usage
from core.rate_limit import LLM_RATE_LIMIT, limiter
from db import get_db
from db_models import User

router = APIRouter()


@router.post("/recommend-cities", response_model=RecommendCitiesResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def recommend_cities_endpoint(
    request: Request,
    body: RecommendCitiesRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> RecommendCitiesResponse:
    reset_usage()
    try:
        return await recommend_cities(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="recommend-cities"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
