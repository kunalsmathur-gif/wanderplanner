from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str    # "user" or "assistant"
    content: str
    config_patch: dict[str, Any] = {}  # real patch from this turn (for history reconstruction)


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    trip_context: dict | None = None   # optional TripConfig snippet for personalization


class ChatResponse(BaseModel):
    reply: str
    role: str = "assistant"
