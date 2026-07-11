"""Chat-refine chain: returns travel reply + structured config patch action."""
from __future__ import annotations

import asyncio
import json
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize
from models.chat import ChatMessage
from models.trip import PinnedPOI, TripConfig


class ChatRefineResponse(BaseModel):
    reply: str
    action_type: Literal["none", "patch_config", "regenerate"]
    config_patch: dict | None = None
    major_change: bool = False
    # Refinement hard-constraints ("Harry Potter test", GTM §2): when the
    # user names an interest, verified places get pinned and reported here
    # so the UI can render commitment chips; unverifiable candidates are
    # listed too — we tell the user what we dropped rather than pin fiction.
    named_interest: str | None = None
    pinned_pois: list[PinnedPOI] = []
    dropped_candidates: list[str] = []


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
  "major_change": false,
  "named_interest": null
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

NAMED INTEREST DETECTION:
- If the user expresses a specific fandom, passion or theme and wants places
  for it in the trip (e.g. "I'm a huge Harry Potter fan", "add some F1
  experiences", "we love street photography"), set "named_interest" to a
  short label for it (e.g. "Harry Potter", "Formula 1", "street photography")
  and action_type to "patch_config" (config_patch may be null — the server
  finds and verifies real matching places itself; do NOT list places in
  config_patch).
- In the reply, say you're finding real verified places for that interest —
  do NOT name specific places yourself.
- Otherwise set "named_interest": null.

GUARDRAILS:
- Only answer travel-related questions.
- Never make bookings or collect payment info.
- Budget always in INR.
- Keep replies concise and friendly.
- If the user asks something non-travel related, set action_type: "none" and politely decline.

Non-travel response: "I'm Anya, WanderPlanner's travel assistant — I can only help with travel questions! 🌍"
"""


async def _apply_interest_pinning(
    resp: ChatRefineResponse, trip_config: TripConfig
) -> ChatRefineResponse:
    """When the refine LLM detected a named interest, expand it to candidate
    places (one small LLM call) and verify each against ingested OSM/wiki
    data. Survivors become hard pins in config_patch; the reply says exactly
    what was pinned and what couldn't be verified. Best-effort throughout —
    any failure leaves the original response untouched."""
    interest = (resp.named_interest or "").strip()
    destination = trip_config.destination.city if trip_config.destination else ""
    if not interest or not destination:
        return resp

    from chains.interest_expansion_chain import expand_interest_to_candidates
    from services.poi_pinning import merge_pins, verify_candidates

    candidates = await expand_interest_to_candidates(interest, destination)
    if not candidates:
        return resp

    pins, dropped = await verify_candidates(candidates, destination, source_interest=interest)
    resp.pinned_pois = pins
    resp.dropped_candidates = dropped

    if pins:
        merged = merge_pins(trip_config.pinned_pois, pins)
        patch = dict(resp.config_patch or {})
        patch["pinned_pois"] = [p.model_dump() for p in merged]
        resp.config_patch = patch
        if resp.action_type == "none":
            resp.action_type = "patch_config"
        names = ", ".join(p.name for p in pins)
        resp.reply += (
            f"\n\n📌 Pinned to your trip for **{interest}**: {names} — "
            "verified real places that will be locked into your itinerary."
        )
        if dropped:
            resp.reply += (
                f"\nI couldn't verify {', '.join(dropped)} against my places "
                "database, so I left those out."
            )
    else:
        resp.reply += (
            f"\n\nI looked for real {interest} spots around {destination} but "
            "couldn't verify any against my places database, so I haven't "
            "pinned anything — better honest than invented!"
        )
    return resp


async def chat_refine(request: ChatRefineRequest) -> ChatRefineResponse:
    if settings.llm_provider == "mock":
        last_msg = request.messages[-1].content if request.messages else ""
        return await _apply_interest_pinning(_mock_refine(last_msg), request.trip_config)

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

    def _call_sync():
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.5,
                max_output_tokens=1024,
            ),
        )

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, _call_sync)
    track_gemini_usage(response, model=settings.gemini_model, purpose="chat_refine")
    raw = response.text

    try:
        cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(cleaned)
        patch = data.get("config_patch")
        if isinstance(patch, dict):
            # Pins may only ever come from OSM/wiki verification — an
            # LLM-authored pinned_pois would bypass the whole point.
            patch.pop("pinned_pois", None)
        resp = ChatRefineResponse(
            reply=data.get("reply", raw),
            action_type=data.get("action_type", "none"),
            config_patch=patch,
            major_change=bool(data.get("major_change", False)),
            named_interest=data.get("named_interest") or None,
        )
    except Exception:
        return ChatRefineResponse(reply=raw, action_type="none", config_patch=None, major_change=False)

    return await _apply_interest_pinning(resp, request.trip_config)


def _mock_refine(user_msg: str) -> ChatRefineResponse:
    msg = user_msg.lower()
    if any(kw in msg for kw in ["harry potter", "f1 ", "formula 1", "fan of"]):
        interest = "Harry Potter" if "harry potter" in msg else "Formula 1"
        return ChatRefineResponse(
            reply=f"Ooh, a {interest} trip! Let me find real, verified places for that…",
            action_type="patch_config",
            config_patch=None,
            major_change=False,
            named_interest=interest,
        )
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
