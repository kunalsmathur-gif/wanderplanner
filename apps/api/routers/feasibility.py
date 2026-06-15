from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models.feasibility import FeasibilityRequest, FeasibilityResponse
from chains.feasibility_chain import check_feasibility

router = APIRouter()


@router.post("/feasibility-check", response_model=FeasibilityResponse)
async def feasibility_check(request: FeasibilityRequest) -> FeasibilityResponse:
    try:
        return await check_feasibility(request.trip_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
