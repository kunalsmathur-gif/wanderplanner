from __future__ import annotations
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str    # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    trip_context: dict | None = None   # optional TripConfig snippet for personalization


class ChatResponse(BaseModel):
    reply: str
    role: str = "assistant"
