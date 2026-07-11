
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from models.feasibility import FeasibilityRequest, FeasibilityResponse
from chains.feasibility_chain import check_feasibility
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter
from core.llm_usage import reset_usage
from core.analytics import flush_llm_usage
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import User

router = APIRouter()


@router.post("/feasibility-check", response_model=FeasibilityResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def feasibility_check(
    request: Request,
    body: FeasibilityRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> FeasibilityResponse:
    reset_usage()
    try:
        return await check_feasibility(body.trip_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="feasibility-check"))
    finally:
        await flush_llm_usage(db, user_id=user.id if user else None)
