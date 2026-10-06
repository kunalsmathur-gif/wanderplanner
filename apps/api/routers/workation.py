"""India workation & long-weekend finder endpoints (docs/plans/
india-workation-finder-plan.md). Never reimplements the underlying logic —
only wires the already-built `services/long_weekend.py` and
`chains/workation_recommend_chain.py` into HTTP routes, mirroring
`routers/recommend_cities.py`'s structure.

Analytics: unlike `itinerary.py`/`feasibility.py`, neither `recommend_cities.py`
nor `chat.py` (the other LLM-backed routers this one mirrors) log an analytics
event inline — the frontend logs `workation_view`/`workation_recommend`/
`workation_handoff` itself via the existing generic `POST /api/analytics`
endpoint (`routers/analytics.py`). This router follows that same convention
rather than inventing a new one.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chains.workation_recommend_chain import (
    WorkationRecommendRequest,
    WorkationRecommendResponse,
    recommend_workation,
)
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from core.errors import sanitize_error
from core.llm_usage import reset_usage
from core.rate_limit import DEFAULT_RATE_LIMIT, LLM_RATE_LIMIT, limiter
from db import get_db
from db_models import User
from services.long_weekend import LongWeekendWindow, drop_elapsed_windows, get_long_weekends

router = APIRouter()


class LongWeekendsResponse(BaseModel):
    windows: list[LongWeekendWindow]


@router.get("/workation/long-weekends", response_model=LongWeekendsResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def long_weekends_endpoint(
    request: Request,
    state: str = Query(..., min_length=1),
    year: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> LongWeekendsResponse:
    # Pure date math, no LLM call — DEFAULT_RATE_LIMIT (same class of endpoint
    # as geocode/best-time), not the tighter LLM_RATE_LIMIT.
    reset_usage()
    try:
        windows = get_long_weekends(state, year)
        windows = drop_elapsed_windows(windows)
        return LongWeekendsResponse(windows=windows)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=sanitize_error(e, context="workation-long-weekends"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)


@router.post("/workation/recommend", response_model=WorkationRecommendResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def workation_recommend_endpoint(
    request: Request,
    body: WorkationRecommendRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> WorkationRecommendResponse:
    reset_usage()
    try:
        return await recommend_workation(body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="workation-recommend"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
