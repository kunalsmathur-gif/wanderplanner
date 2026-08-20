

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chains.feasibility_chain import check_feasibility
from core.analytics import flush_llm_usage, log_event
from core.auth_dependency import get_optional_user
from core.errors import sanitize_error
from core.llm_usage import reset_usage
from core.rate_limit import LLM_RATE_LIMIT, limiter
from db import get_db
from db_models import User
from models.feasibility import FeasibilityRequest, FeasibilityResponse

router = APIRouter()


@router.post("/feasibility-check", response_model=FeasibilityResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def feasibility_check(
    request: Request,
    body: FeasibilityRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> FeasibilityResponse:
    reset_usage()
    started = time.perf_counter()
    try:
        result = await check_feasibility(
            body.trip_config, skip_destination_check=body.skip_destination_check
        )
        # Latency metric (mirrors `itinerary_generated`'s `duration_ms` in
        # routers/itinerary.py) — feeds the admin `/admin/metrics/summary`
        # average/p50/p90 feasibility-check latency figures. Logged on the
        # success path only, same as `itinerary_generated`; failures are
        # covered separately below.
        await log_event(
            db,
            "feasibility_checked",
            user_id=user.id if user else None,
            metadata={
                "destination": (
                    body.trip_config.destination.city
                    if body.trip_config.destination and body.trip_config.destination.city
                    else body.trip_config.destination_country
                ),
                "feasible": result.feasible,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return result
    except Exception as e:
        await log_event(
            db,
            "feasibility_check_failed",
            user_id=user.id if user else None,
            metadata={"duration_ms": round((time.perf_counter() - started) * 1000, 1)},
        )
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="feasibility-check"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
