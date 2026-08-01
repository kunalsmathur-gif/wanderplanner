from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.analytics import log_event
from core.auth_dependency import get_optional_user
from db import get_db
from db_models import ItineraryFeedback, User
from models.itinerary_feedback import (
    FeedbackScope,
    FeedbackSentiment,
    ItineraryFeedbackCreateRequest,
    ItineraryFeedbackResponse,
    ItineraryFeedbackUpdateRequest,
)

router = APIRouter()


def _to_response(feedback: ItineraryFeedback) -> ItineraryFeedbackResponse:
    # `scope`/`sentiment` are plain `String` columns, so the DB layer cannot
    # carry the Literal constraint the API layer does — every write goes
    # through ItineraryFeedbackCreateRequest/UpdateRequest, which validate
    # against exactly these sets. Same shape as routers/auth.py's cast of
    # `settings.cookie_samesite`.
    return ItineraryFeedbackResponse(
        id=str(feedback.id),
        scope=cast(FeedbackScope, feedback.scope),
        day_index=feedback.day_index,
        place_ref=feedback.place_ref,
        sentiment=cast(FeedbackSentiment, feedback.sentiment),
        note=feedback.note,
        created_at=feedback.created_at.isoformat(),
    )


@router.post("/itinerary-feedback", response_model=ItineraryFeedbackResponse)
async def create_itinerary_feedback(
    body: ItineraryFeedbackCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> ItineraryFeedbackResponse:
    feedback = ItineraryFeedback(
        user_id=user.id if user else None,
        trip_config_snapshot=body.trip_config_snapshot,
        scope=body.scope,
        day_index=body.day_index,
        place_ref=body.place_ref,
        sentiment=body.sentiment,
        note=body.note,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    await log_event(
        db,
        "itinerary_feedback_created",
        user_id=user.id if user else None,
        metadata={
            "feedback_id": str(feedback.id),
            "scope": feedback.scope,
            "sentiment": feedback.sentiment,
            "destination": (body.trip_config_snapshot or {}).get("destination"),
        },
    )

    return _to_response(feedback)


@router.patch("/itinerary-feedback/{feedback_id}", response_model=ItineraryFeedbackResponse)
async def update_itinerary_feedback(
    feedback_id: uuid.UUID,
    body: ItineraryFeedbackUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
) -> ItineraryFeedbackResponse:
    # Sentiment-only update, so a day/place thumbs-up/down vote can be
    # flipped without leaving duplicate rows behind (see ItineraryTimeline's
    # vote-change flow) — every other field on a feedback row is immutable.
    feedback = (
        await db.execute(select(ItineraryFeedback).where(ItineraryFeedback.id == feedback_id))
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback.sentiment = body.sentiment
    await db.commit()
    await db.refresh(feedback)

    await log_event(
        db,
        "itinerary_feedback_updated",
        user_id=user.id if user else None,
        metadata={"feedback_id": str(feedback.id), "sentiment": feedback.sentiment},
    )

    return _to_response(feedback)
