"""Lightweight client-side analytics beacons (session starts, external API
calls made from the Next.js server, e.g. the YouTube-thumbnail route which
has no backend counterpart of its own)."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from core.analytics import log_event
from core.auth_dependency import get_optional_user
from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from db import get_db
from db_models import User

router = APIRouter()

_ALLOWED_CLIENT_EVENTS = {"session_start", "youtube_thumbnail_call", "youtube_thumbnail_failed"}


class ClientEventRequest(BaseModel):
    event_type: str
    metadata: Optional[dict] = None


@router.post("/analytics/client-event")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def client_event(
    request: Request,
    body: ClientEventRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.event_type not in _ALLOWED_CLIENT_EVENTS:
        # Silently ignore unknown event types rather than erroring — this is
        # a best-effort beacon, not a critical path.
        return {"status": "ignored"}

    await log_event(db, body.event_type, user_id=user.id if user else None, metadata=body.metadata)
    return {"status": "logged"}
