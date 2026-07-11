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


# Rotated during the actual (long) LLM call so the loader keeps showing
# fresh, engaging progress instead of sitting static for 30-90s. These are
# intentionally vague/varied (not tied to real internal steps) since the LLM
# call itself is a single opaque request with no granular progress signal.
_GENERATION_FILLER_MESSAGES = [
    "Mapping out your days...",
    "Matching activities to your pace...",
    "Balancing everything within budget...",
    "Adding a few local favourites...",
    "Double-checking timings & logistics...",
    "Putting the finishing touches on your plan...",
]


async def _stream_generation(trip_config: TripConfig, db: AsyncSession, user: User) -> AsyncGenerator[str, None]:
    async def send(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    reset_usage()
    total_steps = len(_GENERATION_FILLER_MESSAGES) + 3  # analysing + searching + fillers + finalising
    yield await send("status", {"message": "Analysing your preferences...", "step": 1, "total_steps": total_steps})
    await asyncio.sleep(0)

    yield await send("status", {"message": "Searching destination content...", "step": 2, "total_steps": total_steps})
    await asyncio.sleep(0)

    try:
        task = asyncio.ensure_future(
            asyncio.wait_for(generate_itinerary(trip_config), timeout=settings.llm_timeout_seconds)
        )

        # Poll the in-flight task every few seconds; each tick, emit the next
        # rotating filler message so the UI shows continuous progress during
        # the actual (opaque) LLM generation window.
        step = 2
        msg_idx = 0
        while not task.done():
            done, _pending = await asyncio.wait({task}, timeout=3.0)
            if task in done:
                break
            step = min(step + 1, total_steps - 1)
            yield await send(
                "status",
                {
                    "message": _GENERATION_FILLER_MESSAGES[msg_idx % len(_GENERATION_FILLER_MESSAGES)],
                    "step": step,
                    "total_steps": total_steps,
                },
            )
            msg_idx += 1

        result = await task
        yield await send("status", {"message": "Finalising your schedule...", "step": total_steps, "total_steps": total_steps})
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
