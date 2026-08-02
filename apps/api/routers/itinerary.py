import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chains.itinerary_chain import generate_itinerary
from core.analytics import flush_llm_usage, log_event
from core.auth_dependency import get_current_user
from core.config import settings
from core.errors import sanitize_error
from core.llm_usage import reset_usage
from core.rate_limit import DEFAULT_RATE_LIMIT, LLM_RATE_LIMIT, limiter
from db import get_db
from db_models import User
from models.itinerary import DayPhoto, DayPhotosRequest, GenerateItineraryRequest
from models.trip import TripConfig
from services.pexels import get_day_photos

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

    task = asyncio.ensure_future(
        asyncio.wait_for(generate_itinerary(trip_config), timeout=settings.llm_timeout_seconds)
    )
    try:
        try:
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
                # ⚠️ Both fields were wrong, and neither failed loudly.
                # `destination` passed the `DestinationInput` *model*, which
                # JSONB cannot encode, so every generation's event was lost at
                # commit. `trip_config.days` does not exist at all — duration
                # lives on `dates.duration_days` — so `getattr(..., None)`
                # quietly recorded null on the rare events that did survive.
                # Kept to plain scalars: this feeds admin aggregates, not a
                # replay log, and a dict here is how the first bug happened.
                metadata={
                    "destination": (
                        trip_config.destination.city
                        if trip_config.destination and trip_config.destination.city
                        else trip_config.destination_country
                    ),
                    # Not `dates.duration_days` — `dates` is a plain dict by
                    # design, and that key only exists when the wizard captured
                    # a length explicitly. A trip with concrete start/end dates
                    # has no such key, which is why this recorded null on the
                    # events that did survive. The model method derives it.
                    "days": trip_config.effective_duration_days(),
                },
            )
        finally:
            # Bug fix: if the client disconnects/aborts mid-generation (e.g.
            # the frontend's client-side stall watchdog fires, or the user
            # navigates away), Starlette closes this generator via
            # GeneratorExit at whatever `yield`/`await` it's suspended on —
            # but `task` was scheduled with `asyncio.ensure_future` as an
            # independent Task, so closing *this* generator does NOT
            # automatically cancel it. Left unguarded, the orphaned task
            # keeps running to completion in the background with nobody
            # listening — burning a real Gemini call, Qdrant writes, and a
            # full batch of Pexels image lookups for a result that's simply
            # discarded, for however long generation takes (observed: still
            # running and completing many minutes after the client had
            # already given up and shown a stalled/cancelled request).
            # Cancelling here on every exit path (success, timeout, error,
            # AND client-disconnect) ensures a still-running task is always
            # torn down once nobody can receive its result.
            if not task.done():
                task.cancel()
    except TimeoutError:
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


@router.post("/day-photos")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def day_photos_endpoint(
    request: Request,
    body: DayPhotosRequest,
    user: User = Depends(get_current_user),
) -> list[DayPhoto]:
    """Hero photos for the PDF export, fetched when the user presses Download.

    Previously `generate_itinerary()` awaited this batch inline, so every
    generation paid a metered third-party call (6s timeout) for images only
    the PDF ever displays — the dashboard renders YouTube thumbnails instead.

    Best-effort by contract, exactly as before: `get_day_photos` returns None
    per query rather than raising on a missing key, a network error or an
    empty result, and those become blank entries here so the client can render
    a PDF without images rather than failing the download.

    Authenticated and rate-limited because it proxies a keyed third-party API:
    unauthenticated it would be an open image-search proxy burning our quota.
    """
    photos = await get_day_photos(list(body.queries))
    return [DayPhoto(**photo) if photo else DayPhoto() for photo in photos]
