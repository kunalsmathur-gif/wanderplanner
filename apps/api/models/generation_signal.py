from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

GenerationSignalEventType = Literal["regenerated", "chat_turn", "session_duration"]


class GenerationSignalRequest(BaseModel):
    """Body for POST /api/generation-signal (issue #34).

    `shared` is deliberately not accepted here — it's set internally by
    routers/share.py when a share link is created (see
    services/generation_signals.py::record_share_signal), since the client
    already calls /api/share for that action and a second beacon would just
    be redundant, easy-to-spoof surface area.
    """

    generation_id: str = Field(min_length=1, max_length=40)
    event: GenerationSignalEventType
    # Only meaningful (and required) for "session_duration" — total elapsed
    # seconds since the itinerary was displayed. Capped at 24h to reject
    # garbage/abuse rather than let one bad beacon skew scoring forever.
    value: int | None = Field(default=None, ge=0, le=86400)

    @model_validator(mode="after")
    def _require_value_for_session_duration(self) -> GenerationSignalRequest:
        if self.event == "session_duration" and self.value is None:
            raise ValueError("value is required when event is 'session_duration'")
        return self


class GenerationSignalResponse(BaseModel):
    status: Literal["recorded"] = "recorded"
