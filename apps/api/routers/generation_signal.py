"""Session-signal beacon for the `generated_itineraries` learning flywheel
(issue #34) — POST /api/generation-signal.

Best-effort by design: a client can send several of these per session
(regenerate, chat turns, the final session-duration beacon on unload), and a
failure to record one must never surface as a hard error to the user — this
is analytics feeding a background scoring job, not a critical-path write.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth_dependency import get_optional_user
from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from db import get_db
from db_models import User
from models.generation_signal import GenerationSignalRequest, GenerationSignalResponse
from services.generation_signals import record_generation_signal

router = APIRouter()


@router.post("/generation-signal", response_model=GenerationSignalResponse)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def create_generation_signal(
    request: Request,
    body: GenerationSignalRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> GenerationSignalResponse:
    await record_generation_signal(
        db,
        generation_id=body.generation_id,
        event=body.event,
        value=body.value,
        user_id=user.id if user else None,
    )
    return GenerationSignalResponse()
