import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chains.itinerary_chain import generate_itinerary
from core.analytics import log_event, flush_llm_usage
from core.auth_dependency import get_current_user
from core.config import settings
from core.errors import sanitize_error
from core.rate_limit import LLM_RATE_LIMIT, limiter
from core.llm_usage import reset_usage
from db import get_db
from db_models import User
from models.itinerary import GenerateItineraryRequest
from models.trip import TripConfig

router = APIRouter()


async def _stream_generation(trip_config: TripConfig, db: AsyncSession, user: User) -> AsyncGenerator[str, None]:
    async def send(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    reset_usage()
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
        await log_event(
            db,
            "itinerary_generated",
            user_id=user.id,
            metadata={"destination": getattr(trip_config, "destination", None), "days": getattr(trip_config, "days", None)},
        )
    except asyncio.TimeoutError:
        yield await send("error", {
            "code": "LLM_TIMEOUT",
            "message": "Generation timed out. Please try again.",
            "retryable": True,
        })
        await log_event(db, "itinerary_failed", user_id=user.id, metadata={"reason": "timeout"})
    except Exception as exc:
        yield await send("error", {
            "code": "GENERATION_FAILED",
            "message": sanitize_error(exc, context="generate-itinerary"),
            "retryable": True,
        })
        await log_event(db, "itinerary_failed", user_id=user.id, metadata={"reason": "exception"})
    finally:
        await flush_llm_usage(db, user_id=user.id)


@router.post("/generate-itinerary")
@limiter.limit(LLM_RATE_LIMIT)
async def generate_itinerary_endpoint(
    request: Request,
    body: GenerateItineraryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Auth is enforced here server-side regardless of any frontend gating —
    # generating an itinerary always requires a signed-in account.
    return StreamingResponse(
        _stream_generation(body.trip_config, db, user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
