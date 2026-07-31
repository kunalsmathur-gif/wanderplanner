from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

_MAX_NOTES_WORDS = 100


class AgentLeadCreateRequest(BaseModel):
    email: EmailStr
    destination: str = Field(min_length=1, max_length=120)
    trip_config_summary: dict[str, Any] = Field(default_factory=dict)
    # Free-text ask from the traveler, capped at 100 words so the email stays
    # a quick brief rather than a full re-statement of the trip.
    custom_notes: str | None = Field(default=None, max_length=1000)
    # Rendered day-by-day itinerary (simple HTML) to embed directly in the
    # agent-facing email body, in addition to the PDF attachment below.
    itinerary_html: str | None = None
    # Base64-encoded PDF (no `data:` prefix), generated client-side by the
    # same @react-pdf/renderer document used for the "Download PDF" button.
    pdf_base64: str | None = None

    @field_validator("custom_notes")
    @classmethod
    def _limit_notes_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        word_count = len(v.split())
        if word_count > _MAX_NOTES_WORDS:
            raise ValueError(f"custom_notes must be at most {_MAX_NOTES_WORDS} words (got {word_count})")
        return v


class AgentLeadCreateResponse(BaseModel):
    id: str


class AgentLeadAdminResponse(BaseModel):
    id: str
    user_id: str | None
    email: str
    destination: str
    trip_config_summary: dict[str, Any]
    custom_notes: str | None
    created_at: str
    responded_at: str | None
    escalated_at: str | None
    reassurance_sent_at: str | None
    marked_booked_at: str | None
    status: str
    response_time_hours: float | None

