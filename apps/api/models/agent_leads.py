from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class AgentLeadCreateRequest(BaseModel):
    email: EmailStr
    destination: str = Field(min_length=1, max_length=120)
    trip_config_summary: dict[str, Any] = Field(default_factory=dict)


class AgentLeadCreateResponse(BaseModel):
    id: str


class AgentLeadAdminResponse(BaseModel):
    id: str
    user_id: str | None
    email: str
    destination: str
    trip_config_summary: dict[str, Any]
    created_at: str
    responded_at: str | None
    escalated_at: str | None
    reassurance_sent_at: str | None
    marked_booked_at: str | None
    status: str
    response_time_hours: float | None
