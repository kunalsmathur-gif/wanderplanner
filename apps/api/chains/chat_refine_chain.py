"""Chat-refine chain: returns travel reply + structured config patch action."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel

from core.config import settings
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize
from core.validation import normalise_choice_fields
from models.chat import ChatMessage
from models.trip import DayCostPreference, PinnedPOI, TripConfig

logger = logging.getLogger(__name__)


def _is_transient_llm_error(exc: Exception) -> bool:
    """Gemini overload/availability blips worth one cheap retry — matched on
    the error text because google.genai error classes vary across versions."""
    text = repr(exc)
    return any(tok in text for tok in (
        "503", "500", "502", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
        "overloaded", "DeadlineExceeded", "429",
    ))


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
- If the user expresses a specific interest, passion, fandom or theme they
  want the trip to serve, set "named_interest" to a short label for it and
  action_type to "patch_config" (config_patch may be null — the server finds
  and verifies real matching places itself; do NOT list places in
  config_patch).
- This covers ANY concrete interest, not just pop-culture fandoms: fandoms
  ("I'm a huge Harry Potter fan" → "Harry Potter", "add some F1 experiences"
  → "Formula 1"), activities ("we love street photography" → "street
  photography"), and cultural/thematic interests ("I love zen gardens and
  quiet temples" → "zen gardens", "I want the Portuguese colonial heritage
  side" → "Portuguese heritage", "historic palaces and botanical gardens" →
  "historic palaces and gardens").
- Detect it even when phrased as a question about the destination ("what
  does Bengaluru have for palace lovers?" → "historic palaces") — set
  named_interest and let the server find verified places.
- A user naming SPECIFIC PLACES they want included counts too ("I really
  want to see Tanah Lot", "make sure we do the Golden Temple", "must include
  Meiji Shrine") → set named_interest to those place names and action_type
  to "patch_config". A named place is a request to pin, and the server has
  to verify it before it can be honoured — routing it anywhere else means
  nothing is ever pinned.
- In the reply, say you're finding real verified places for that interest —
  do NOT name specific places yourself, even when answering a question.
- Otherwise set "named_interest": null.

🔴 NEVER CLAIM SOMETHING IS PINNED. You cannot pin anything — only the server
can, after verifying the place exists in our OpenStreetMap/Wikivoyage data,
and it appends its own "📌 Pinned to your trip" line to your reply when it
does. So never write "I've added X to your pinned places", "X is locked in",
"that's been added to your itinerary", or any past-tense claim that a place
is now part of the trip. Say what you are about to do, not what you have
done: "Let me find the verified places for that" is correct. A past-tense
claim is a promise you have no way to keep, and when verification finds
nothing it becomes a straightforward lie to the traveller.

GUARDRAILS:
- Only answer travel-related questions.
- Never make bookings or collect payment info.
- Budget always in INR.
- Keep replies concise and friendly.
- If the user asks something non-travel related, set action_type: "none" and politely decline.

Non-travel response: "I'm Anya, WanderPlanner's travel assistant — I can only help with travel questions! 🌍"

FRESHNESS CAVEAT HINT (only present when the user's latest message reads as time-sensitive —
weather, live prices, strikes/disruptions, "right now"/"this week" style questions):
{router_hint}
Rules for using it: if present, weave the caveat naturally into your reply instead of answering
as if you have current, up-to-the-minute information — mention that conditions can change and
suggest double-checking a live/official source closer to the trip. Never disclose this as a
system limitation ("I don't have real-time data") — just naturally hedge the specific claim.
"""


# Phrases that falsely claim a place has been pinned — the same class of bug
# as wizard_chat_chain.py's _HALLUCINATED_GENERATION_RE, and caught the same
# way: the model narrating an action it has no way to perform. Observed live
# (2026-08-04) on "I really want to see Tanah Lot on this trip", which returned
# named_interest=null and pinned_pois=[] while replying "Got it! I've added
# Tanah Lot to your pinned points of interest for this trip." Only the server
# can pin (see _apply_interest_pinning), so any such claim in a turn that
# pinned nothing is false by construction.
#
# Deliberately anchored on the past/perfect forms ("I've added", "I have
# pinned", "is locked in") — NOT the future or offer forms ("I'll add",
# "shall I pin"), which are legitimate things to say before verification runs.
_HALLUCINATED_PIN_RE = re.compile(
    r"\b(?:i'?ve|i\s+have)\s+(?:added|pinned|locked|included|saved)\b"
    r"|\b(?:added|pinned|locked)\s+(?:it|that|them|this)\s+(?:to|into|in)\b"
    r"|\bis\s+(?:now\s+)?(?:pinned|locked\s+in)\b"
    r"|\bhas\s+been\s+(?:added|pinned|locked)\b",
    re.IGNORECASE,
)

# What we say instead. Kept generic (no place name) because the whole point is
# that we could not confirm which place, if any, is real.
_PIN_CLAIM_RETRACTION = (
    "I can only lock in places I've verified against my places database, and I "
    "haven't verified anything for that yet — so nothing is pinned. Tell me the "
    "kind of thing you're after (for example \"iconic temples and sunset "
    "views\") and I'll go find the real ones."
)


# "make day 3 cheaper" — parsed deterministically from the user's own text
# rather than trusted from the LLM, for the same reason pins are verified
# server-side: the day number is a structural index into the itinerary, and a
# model that miscounts it silently re-costs the wrong day. Ordinals are
# included because people say "the third day" as readily as "day 3".
_ORDINAL_DAYS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "last": -1,
}
_DAY_REF_RE = re.compile(
    r"\bday\s*(\d{1,2})\b"
    r"|\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last)\s+day\b",
    re.IGNORECASE,
)
_CHEAPER_RE = re.compile(
    r"\b(cheap(?:er|est)?|budget|less\s+expensive|save|saving|spend\s+less|"
    r"lower\s+the\s+cost|cut\s+(?:the\s+)?cost|affordable|economical|sasta)\b",
    re.IGNORECASE,
)
# `luxur\w*` is a deliberate STEM, not an oversight: a bare `\bluxur\b` cannot
# match "luxurious" or "luxury" because there is no word boundary after the
# stem. core/budget_estimator.py's PREMIUM_KEYWORDS documents the same trap.
_PRICIER_RE = re.compile(
    r"\b(splurge\w*|spend\s+more|fancy|luxur\w*|premium|treat\s+ourselves|"
    r"go\s+all\s+out|upgrade)\b",
    re.IGNORECASE,
)


def _parse_day_cost_request(
    text: str, total_days: int | None
) -> tuple[int, Literal["cheaper", "pricier"]] | None:
    """Extract (day_number, direction) from a message like "make day 3 cheaper".

    Returns None when the message doesn't name BOTH a day and a spend
    direction — "make it cheaper" (no day) is a trip-wide budget change that
    belongs to the existing `regenerate` path, and "tell me about day 3" names
    a day but asks for nothing.
    """
    day_match = _DAY_REF_RE.search(text or "")
    if not day_match:
        return None
    if day_match.group(1):
        day = int(day_match.group(1))
    else:
        day = _ORDINAL_DAYS[day_match.group(2).lower()]
    if day == -1:                       # "the last day"
        if not total_days:
            return None                 # can't resolve it; don't guess a day
        day = total_days
    if total_days and not 1 <= day <= total_days:
        return None                     # a day this trip doesn't have
    if day < 1:
        return None

    # Direction: check "pricier" first — "splurge on day 3, save elsewhere"
    # mentions both, and the day named is the one being splurged on.
    if _PRICIER_RE.search(text):
        return day, "pricier"
    if _CHEAPER_RE.search(text):
        return day, "cheaper"
    return None


def _apply_day_cost_preference(
    resp: ChatRefineResponse, trip_config: TripConfig, last_user_text: str
) -> ChatRefineResponse:
    """Turn "make day 3 cheaper" into a real, structured config change.

    Before this existed the refine LLM answered "I'll make a note to optimize
    Day 3" and produced `action_type: "none"` with no patch — nothing was
    stored, nothing regenerated, and the promise was never kept (live-observed
    2026-08-04). The itinerary is regenerated by the client whenever the patch
    carries `day_cost_preferences`, exactly as it does for `pinned_pois`.
    """
    parsed = _parse_day_cost_request(last_user_text, trip_config.effective_duration_days())
    if not parsed:
        return resp
    day, direction = parsed

    existing = list(getattr(trip_config, "day_cost_preferences", None) or [])
    merged = [*existing, DayCostPreference(day_number=day, direction=direction)]
    # The model validator dedupes (last write wins) and caps — go through it
    # rather than reimplementing that here, so the two can never disagree.
    normalised = TripConfig(day_cost_preferences=merged).day_cost_preferences

    patch = dict(resp.config_patch or {})
    patch["day_cost_preferences"] = [p.model_dump() for p in normalised]
    resp.config_patch = patch
    resp.action_type = "patch_config"
    # Not `major_change`: this re-plans one day, and routing it through the
    # confirm-then-regenerate path would put a modal in front of a small,
    # obviously-reversible edit.
    resp.major_change = False
    verb = "lighter on the wallet" if direction == "cheaper" else "more of a splurge"
    resp.reply = (
        f"Done — I'm making day {day} {verb} and rebuilding your itinerary now. "
        "Anything you've pinned stays exactly where it is."
    )
    return resp


def _strip_false_pin_claim(resp: ChatRefineResponse) -> ChatRefineResponse:
    """Replace a reply that claims a pin with the truth, when nothing pinned.

    Runs AFTER _apply_interest_pinning, so `resp.pinned_pois` is final. A
    turn that really did pin something has the server-authored 📌 block
    appended and is left alone.
    """
    if resp.pinned_pois:
        return resp
    if not _HALLUCINATED_PIN_RE.search(resp.reply or ""):
        return resp
    logger.warning(
        "chat_refine reply claimed a pin but nothing was pinned; retracting"
    )
    resp.reply = _PIN_CLAIM_RETRACTION
    return resp


async def _apply_interest_pinning(
    resp: ChatRefineResponse, trip_config: TripConfig
) -> ChatRefineResponse:
    """When the refine LLM detected a named interest, expand it to candidate
    places (one small LLM call) and verify each against ingested OSM/wiki
    data. Survivors become hard pins in config_patch; the reply says exactly
    what was pinned and what couldn't be verified. Best-effort throughout —
    any failure leaves the original response untouched."""
    interest = (resp.named_interest or "").strip()
    if not interest:
        # Deterministic backstop for a live-observed failure mode (2026-07-13
        # eval, RF-004/RF-014): the refine LLM routes a concrete interest into
        # a themes config_patch instead of named_interest. A theme the user
        # just added IS a named interest, so derive the label from the new
        # themes — zero extra LLM calls, and verification still gates pins.
        patch_themes = (resp.config_patch or {}).get("themes")
        if isinstance(patch_themes, list):
            existing = {str(t).strip().lower() for t in (trip_config.themes or [])}
            new_themes = [
                str(t).strip() for t in patch_themes
                if isinstance(t, str) and t.strip() and t.strip().lower() not in existing
            ]
            if new_themes:
                interest = " and ".join(new_themes[:2])
                resp.named_interest = interest
    destination = trip_config.destination.city if trip_config.destination else ""
    if not interest or not destination:
        return resp

    from chains.interest_expansion_chain import expand_interest_to_candidates
    from services.poi_pinning import merge_pins, verify_candidates

    candidates = await expand_interest_to_candidates(interest, destination)
    if candidates:
        pins, dropped = await verify_candidates(
            candidates, destination, source_interest=interest
        )
    else:
        # 🔴 This used to `return resp` early, which silently skipped the
        # honesty message below. Expansion coming back empty and expansion
        # returning candidates that all fail verification are the SAME thing
        # to the user — we found nothing real — so they must say the same
        # thing. Without this, the live "Harry Potter in Goa" case answered
        # "I'll look for real, verified Harry Potter places ✨" and then never
        # mentioned it again: an unkept promise, which is worse than the
        # invention we refuse to make. Skips the verification call rather
        # than passing it an empty list, since there is nothing to scroll for.
        pins, dropped = [], []
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
                "database — they may still be real, but please check reviews "
                "on Google Maps/Reddit before building your plan around them."
            )
    else:
        resp.reply += (
            f"\n\nI looked for real {interest} spots around {destination} but "
            "couldn't verify any against my places database, so I haven't "
            "pinned anything — better honest than invented! If you have "
            "specific places in mind, please check reviews on Google Maps/"
            "Reddit before building your plan around them."
        )
    return resp


async def chat_refine(request: ChatRefineRequest) -> ChatRefineResponse:
    if settings.llm_provider == "mock":
        last_msg = request.messages[-1].content if request.messages else ""
        return _strip_false_pin_claim(
            _apply_day_cost_preference(
                await _apply_interest_pinning(_mock_refine(last_msg), request.trip_config),
                request.trip_config,
                last_msg,
            )
        )

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed.")

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    trip_json = neutralize(request.trip_config.model_dump_json(indent=2), context="trip configuration")

    router_hint = ""
    if settings.agentic_router_enabled:
        try:
            from services.query_router import route_query
            last_user_msg = next((m.content for m in reversed(request.messages) if m.role == "user"), None)
            router_hint = route_query(last_user_msg).note or ""
        except Exception:
            router_hint = ""

    system_prompt = _REFINE_SYSTEM_PROMPT.format(
        trip_config_json=trip_json,
        router_hint=router_hint or "(not applicable this turn)",
    )

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
    # One cheap retry on transient Gemini 5xx/quota blips (hit live 2026-07-12:
    # a single 503 UNAVAILABLE bubbled straight to the frontend; the
    # generation chain retries but refine didn't).
    for attempt in range(2):
        try:
            response = await loop.run_in_executor(None, _call_sync)
            break
        except Exception as exc:
            if attempt == 0 and _is_transient_llm_error(exc):
                logger.warning("chat_refine transient LLM error (%s); retrying once…", exc)
                await asyncio.sleep(2)
                continue
            raise
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
            # Same canonicalisation the wizard applies: this patch goes straight
            # into the frontend's config store (ChatPanel.tsx::updateConfig),
            # which never re-validates through TripConfig.
            patch = normalise_choice_fields(patch)
        resp = ChatRefineResponse(
            reply=data.get("reply", raw),
            action_type=data.get("action_type", "none"),
            config_patch=patch,
            major_change=bool(data.get("major_change", False)),
            named_interest=data.get("named_interest") or None,
        )
    except Exception:
        return ChatRefineResponse(reply=raw, action_type="none", config_patch=None, major_change=False)

    last_user_text = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )
    return _strip_false_pin_claim(
        _apply_day_cost_preference(
            await _apply_interest_pinning(resp, request.trip_config),
            request.trip_config,
            last_user_text,
        )
    )


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
