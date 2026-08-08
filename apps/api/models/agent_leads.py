from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

_MAX_NOTES_WORDS = 100

# "itinerary": the happy-path "Get this itinerary booked" CTA on an
# already-generated itinerary. "infeasible_budget": the "talk to a human"
# option offered when the feasibility gate blocks generation outright. Kept
# as a closed set so a typo/new caller can't silently create an untracked
# lead type that the admin console and per-day dedup guard don't know about.
AgentLeadSource = Literal["itinerary", "infeasible_budget"]


class AgentLeadCreateRequest(BaseModel):
    email: EmailStr
    destination: str = Field(min_length=1, max_length=120)
    source: AgentLeadSource = "itinerary"
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
    # True when this call was a same-day repeat of the same source type from
    # the same requester — no new lead/email was created, `id` refers to the
    # existing one from earlier today. Lets the caller show "already sent"
    # instead of a second false "request sent" confirmation.
    duplicate: bool = False


class AgentLeadAdminResponse(BaseModel):
    id: str
    user_id: str | None
    email: str
    destination: str
    source: str
    trip_config_summary: dict[str, Any]
    custom_notes: str | None
    created_at: str
    responded_at: str | None
    escalated_at: str | None
    reassurance_sent_at: str | None
    marked_booked_at: str | None
    status: str
    response_time_hours: float | None
    # `status` collapses to a single label for the badge; these two carry the
    # detail behind a "responded_late", so the dashboard can say *why* it was
    # late without re-deriving it from the timestamps client-side. They are
    # meaningful on unresponded leads too: `sla_breached` goes true the moment
    # the clock passes the SLA, whether or not anyone has replied yet.
    sla_breached: bool = False
    was_escalated: bool = False

