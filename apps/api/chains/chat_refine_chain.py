"""Chat-refine chain: returns travel reply + structured config patch action."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.prompt_guard import neutralize
from models.chat import ChatMessage
from models.trip import TripConfig


class ChatRefineResponse(BaseModel):
    reply: str
    action_type: Literal["none", "patch_config", "regenerate"]
    config_patch: dict | None = None
    major_change: bool = False


class ChatRefineRequest(BaseModel):
    messages: list[ChatMessage]
    trip_config: TripConfig


_REFINE_SYSTEM_PROMPT = """\
You are Anya, WanderPlanner's friendly AI travel assistant.

ROLE: Help refine the user's active trip plan based on their message. You can:
1. Answer travel questions factually.
2. Suggest changes to their trip configuration.
3. Detect when the user wants to change specific trip parameters.

CURRENT TRIP CONFIG:
{trip_config_json}

RESPONSE FORMAT — always respond with ONLY this JSON (no markdown):
{{
  "reply": "Your friendly conversational reply to the user (markdown ok here)",
  "action_type": "none" | "patch_config" | "regenerate",
  "config_patch": null or {{ ...only the fields that changed... }},
  "major_change": false
}}

ACTION RULES:
- "none": For general travel questions, tips, recommendations — no config change needed.
- "patch_config": For small preference changes (accommodation style, pace, themes, personas).
  Set config_patch to ONLY the changed fields (e.g. {{"pace": "relaxed"}}).
  Set major_change: false.
- "regenerate": For changes that fundamentally alter the itinerary:
  - Destination change
  - Date change (start/end dates or season)
  - Group size change (adults/kids/seniors added or removed)
  - Budget change of >20%
  Set config_patch with the changed fields.
  Set major_change: true.
  In the reply, ask the user to confirm regeneration.

GUARDRAILS:
- Only answer travel-related questions.
- Never make bookings or collect payment info.
- Budget always in INR.
- Keep replies concise and friendly.
- If the user asks something non-travel related, set action_type: "none" and politely decline.

Non-travel response: "I'm Anya, WanderPlanner's travel assistant — I can only help with travel questions! 🌍"
"""


async def chat_refine(request: ChatRefineRequest) -> ChatRefineResponse:
    if settings.llm_provider == "mock":
        last_msg = request.messages[-1].content if request.messages else ""
        return _mock_refine(last_msg)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    trip_json = neutralize(request.trip_config.model_dump_json(indent=2), context="trip configuration")
    system_prompt = _REFINE_SYSTEM_PROMPT.format(trip_config_json=trip_json)

    history = request.messages[-10:]
    contents = []
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=neutralize(msg.content, context="chat message"))]))

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
                max_output_tokens=1024,
            ),
        )
        return response.text

    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(None, _call_sync)

    try:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(cleaned)
        return ChatRefineResponse(
            reply=data.get("reply", raw),
            action_type=data.get("action_type", "none"),
            config_patch=data.get("config_patch"),
            major_change=bool(data.get("major_change", False)),
        )
    except Exception:
        return ChatRefineResponse(reply=raw, action_type="none", config_patch=None, major_change=False)


def _mock_refine(user_msg: str) -> ChatRefineResponse:
    msg = user_msg.lower()
    if any(kw in msg for kw in ["relax", "slower", "easy pace"]):
        return ChatRefineResponse(
            reply="Sure! I've updated your trip pace to **Relaxed** — more downtime and fewer rushed activities. ✅",
            action_type="patch_config",
            config_patch={"pace": "relaxed"},
            major_change=False,
        )
    if any(kw in msg for kw in ["change destination", "go to", "switch to"]):
        return ChatRefineResponse(
            reply="Got it! Changing the destination will regenerate your itinerary. Shall I proceed?",
            action_type="regenerate",
            config_patch=None,
            major_change=True,
        )
    if any(kw in msg for kw in ["add", "person", "friend", "family", "bring"]):
        return ChatRefineResponse(
            reply="Adding a traveller will affect costs and room allocation — this will regenerate your itinerary. Want to continue?",
            action_type="regenerate",
            config_patch=None,
            major_change=True,
        )
    return ChatRefineResponse(
        reply="Great question! I can help you refine your trip. What specifically would you like to change?",
        action_type="none",
        config_patch=None,
        major_change=False,
    )
