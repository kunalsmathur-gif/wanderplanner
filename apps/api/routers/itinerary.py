from __future__ import annotations
import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from chains.itinerary_chain import generate_itinerary
from core.config import settings
from models.itinerary import GenerateItineraryRequest
from models.trip import TripConfig

router = APIRouter()


async def _stream_generation(trip_config: TripConfig) -> AsyncGenerator[str, None]:
    async def send(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    yield await send("status", {"message": "Analysing your preferences...", "step": 1, "total_steps": 4})
    await asyncio.sleep(0)

    yield await send("status", {"message": "Searching destination content...", "step": 2, "total_steps": 4})
    await asyncio.sleep(0)

    try:
        result = await asyncio.wait_for(
            generate_itinerary(trip_config),
            timeout=settings.llm_timeout_seconds,
        )
        yield await send("status", {"message": "Finalising your schedule...", "step": 4, "total_steps": 4})
        yield await send("data", result.model_dump())
    except asyncio.TimeoutError:
        yield await send("error", {
            "code": "LLM_TIMEOUT",
            "message": "Generation timed out. Please try again.",
            "retryable": True,
        })
    except Exception as exc:
        yield await send("error", {
            "code": "GENERATION_FAILED",
            "message": str(exc),
            "retryable": True,
        })


@router.post("/generate-itinerary")
async def generate_itinerary_endpoint(request: GenerateItineraryRequest):
    return StreamingResponse(
        _stream_generation(request.trip_config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
