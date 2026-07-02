
from fastapi import APIRouter, HTTPException, Request
from models.feasibility import FeasibilityRequest, FeasibilityResponse
from chains.feasibility_chain import check_feasibility
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter

router = APIRouter()


@router.post("/feasibility-check", response_model=FeasibilityResponse)
@limiter.limit(LLM_RATE_LIMIT)
async def feasibility_check(request: Request, body: FeasibilityRequest) -> FeasibilityResponse:
    try:
        return await check_feasibility(body.trip_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error(e, context="feasibility-check"))
