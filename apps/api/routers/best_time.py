from __future__ import annotations
from fastapi import APIRouter
from models.common import BestTimeResponse
from services.best_time import get_best_time

router = APIRouter()


@router.get("/best-time/{destination}", response_model=BestTimeResponse)
async def best_time(destination: str):
    return await get_best_time(destination)
