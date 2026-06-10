from fastapi import APIRouter, Query
from models.common import GeocodeResponse
from services.geocode import geocode_city

router = APIRouter()


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode(q: str = Query(..., min_length=2)):
    return await geocode_city(q)
