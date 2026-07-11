from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.itinerary import CompareDestinationsRequest, ComparisonResponse
from services.comparison import build_comparison
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter
from core.llm_usage import reset_usage
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import User

router = APIRouter()


@router.post("/compare-destinations", response_model=ComparisonResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def compare_destinations(
    request: Request,
    body: CompareDestinationsRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    reset_usage()
    try:
        return await build_comparison(body.destinations, body.trip_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="compare-destinations"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
