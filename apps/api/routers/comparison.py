from __future__ import annotations
from fastapi import APIRouter, Query
from models.itinerary import CompareDestinationsRequest, ComparisonResponse
from services.comparison import build_comparison

router = APIRouter()


@router.post("/compare-destinations", response_model=ComparisonResponse)
async def compare_destinations(request: CompareDestinationsRequest):
    return await build_comparison(request.destinations, request.trip_config)
