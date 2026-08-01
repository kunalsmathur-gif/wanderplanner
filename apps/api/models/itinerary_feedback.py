from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

FeedbackScope = Literal["itinerary", "day", "place"]
FeedbackSentiment = Literal["missed_the_mark", "thumbs_up", "thumbs_down"]


class ItineraryFeedbackCreateRequest(BaseModel):
    trip_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    scope: FeedbackScope
    day_index: int | None = Field(default=None, ge=0)
    place_ref: str | None = Field(default=None, min_length=1, max_length=200)
    sentiment: FeedbackSentiment
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _require_scope_fields(self) -> ItineraryFeedbackCreateRequest:
        # "day" and "place" scope reactions are tied to a specific day, and
        # "place" additionally needs the item they reacted to — reject rather
        # than silently defaulting, so a client bug never gets recorded as
        # itinerary-wide feedback.
        if self.scope in ("day", "place") and self.day_index is None:
            raise ValueError("day_index is required when scope is 'day' or 'place'")
        if self.scope == "place" and not self.place_ref:
            raise ValueError("place_ref is required when scope is 'place'")
        return self


class ItineraryFeedbackUpdateRequest(BaseModel):
    sentiment: FeedbackSentiment


class ItineraryFeedbackResponse(BaseModel):
    id: str
    scope: FeedbackScope
    day_index: int | None
    place_ref: str | None
    sentiment: FeedbackSentiment
    note: str | None
    created_at: str
