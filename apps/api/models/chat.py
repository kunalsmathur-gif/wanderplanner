from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.validation import (
    MAX_CHAT_HISTORY,
    MAX_TRIP_CONTEXT_CHARS,
    ChatMessageText,
    ShortLabel,
)


class ChatMessage(BaseModel):
    role: ShortLabel    # "user" or "assistant"
    content: ChatMessageText
    config_patch: dict[str, Any] = {}  # real patch from this turn (for history reconstruction)


class ChatRequest(BaseModel):
    # chains/chat_chain.py only ever sends the last 10 turns to the model, but
    # the whole list is still parsed and validated first — the cap is on what
    # the request may carry, not on what the prompt uses.
    messages: list[ChatMessage] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY)
    trip_context: dict | None = None   # optional TripConfig snippet for personalization

    @field_validator('trip_context')
    @classmethod
    def bound_trip_context(cls, v: dict | None) -> dict | None:
        """`_build_prompt` serialises this straight into the system prompt, so
        its serialised size is the thing that matters, not its key count."""
        if v is None:
            return v
        serialised = json.dumps(v, default=str)
        if len(serialised) > MAX_TRIP_CONTEXT_CHARS:
            raise ValueError(
                f"trip_context must serialise to at most {MAX_TRIP_CONTEXT_CHARS} characters "
                f"(received {len(serialised)})"
            )
        return v


class ChatResponse(BaseModel):
    reply: str
    role: str = "assistant"
