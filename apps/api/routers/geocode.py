from __future__ import annotations
from fastapi import APIRouter, Query
from models.common import GeocodeResponse
from services.geocode import geocode_city

router = APIRouter()


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode(
    q: str = Query(..., min_length=2),
    countrycodes: str = Query(default=""),
):
    return await geocode_city(q, countrycodes=countrycodes)
