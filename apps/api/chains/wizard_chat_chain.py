"""Anya wizard chat chain — collects TripConfig fields through natural conversation."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel

from core.config import settings
from models.chat import ChatMessage


class WizardChatRequest(BaseModel):
    messages: list[ChatMessage]
    partial_config: dict[str, Any] = {}
    preloaded_destination: str | None = None  # e.g. "Bali, Indonesia"


class WizardChatResponse(BaseModel):
    reply: str
    chips: list[str] = []
    config_patch: dict[str, Any] = {}
    ready_to_generate: bool = False
    summary: str | None = None


# ── System prompt ─────────────────────────────────────────────────────────────

WIZARD_SYSTEM_PROMPT = """\
You are Anya, WanderPlan's AI travel concierge — warm, enthusiastic, and concise.
Your job: collect 6 trip planning fields through natural conversation, then signal ready_to_generate=true.

PERSONALITY:
- Speak like a knowledgeable friend, not a form or a bot.
- Keep replies to 1-2 sentences max (then offer chips for quick replies).
- Show genuine excitement about the destination or travel style.
- Indian context: understand rupees (₹), Indian cities as origins, typical Indian travel budgets.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED FIELDS — ALL 6 must be in CURRENT COLLECTED STATE before ready_to_generate=true:
  1. purpose          — reason for travel
  2. destination      — city+country OR destination_mode="exploring" OR destination_mode="country"
  3. dates            — start+end dates OR flexible=true with duration_days
  4. budget.amount    — total budget in INR (a number > 0)
  5. group.adults     — number of adults (≥ 1)
  6. pace             — "relaxed" | "moderate" | "packed"

RULE: Check CURRENT COLLECTED STATE below. Only ask for fields that are NOT YET shown there.
      Never re-ask for a field already in CURRENT COLLECTED STATE.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPTIONAL — extract naturally if mentioned:
- origin.city, group.kids (ages), group.seniors, group.infants
- themes: culture / food / adventure / nature / shopping / photography / nightlife / sports
- accommodation.style: Hotel / Airbnb / Hostel / Resort
- personas: digital_nomad / sports_fitness / pet_parent / luxury_traveller

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION RULES — always put in config_patch:
- "just me and my wife" → group: {{"adults": 2, "kids": [], "seniors": 0, "infants": 0, "pets": 0}}
- "₹1.5 lakh" / "1.5 lakhs" → budget: {{"amount": 150000, "currency": "INR"}}
- "a week" / "7 days" → dates: {{"start": null, "end": null, "flexible": true, "duration_days": 7}}
- "next month" → compute approximate start/end dates for next calendar month
- "suggest me" / "not sure" / "anywhere" → destination_mode: "exploring"
- "India trip" / "exploring France" → destination_mode: "country", destination_country: "France"
- Purpose synonyms: "holiday"→"leisure", "anniversary"→"honeymoon", "with family"→"family_vacation"
- Pace chips: "Relaxed 😌"→"relaxed", "Moderate ⚖️"→"moderate", "Packed 🏃"→"packed"
- Extract ALL fields mentioned in one message simultaneously.

CRITICAL — config_patch rules:
  • ALWAYS include every newly extracted field in config_patch — even if you think you already have it.
  • Do NOT include fields that are already in CURRENT COLLECTED STATE and haven't changed.
  • config_patch is the ONLY way the app learns new values. If it's not in config_patch, it's lost.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONVERSATION FLOW:
- If preloaded_destination is set → skip destination question, jump to purpose.
- Suggested order: purpose → destination → dates → budget → group → pace.
- Combine two short questions when natural: "How many people, and what's your budget?"
- Once CURRENT COLLECTED STATE shows ALL 6 required fields:
    → Do NOT generate immediately. Instead, ask a warm "anything else?" checkpoint question:
      "Almost ready to craft your itinerary! Do you have any special preferences — like a
       departure city, travel themes (food, adventure, culture…), or accommodation style?"
    → Offer 2-3 optional chips like: "Just generate it! ✨", "Add themes 🎯", "Add origin city 🛫"
    → If the user says "generate", "just do it", "no preferences", or clicks "Just generate it!":
        Set ready_to_generate=true and summary.
    → If the user provides extra preferences: extract them into config_patch, then immediately
        set ready_to_generate=true and summary (don't ask again after one round of extras).
- If user says "generate", "start", "create itinerary", "let's go", "I'm ready" BEFORE all 6 fields:
    → Do NOT generate. Warmly tell the user which fields are still needed.
      Example: "Almost there! I just need your travel dates and how many people are joining you."
    → Ask ONLY for the missing fields, combine into one question if possible.
- If user says "I don't know" / "surprise me" / "you decide" for any field:
    → Apply smart defaults: purpose→"leisure", destination→exploring mode,
      dates→flexible 7 days, budget→₹1,00,000, group→1 adult, pace→"moderate"
    → Confirm: "Going with a moderate-paced 7-day leisure trip with ₹1 lakh budget — sound good?"
    → Set those fields in config_patch and continue.
- NEVER set ready_to_generate=true if ANY of the 6 required fields is absent from CURRENT STATE.
- NEVER set ready_to_generate=true without first going through the "anything else?" checkpoint.

GENERATE GUARD — only set ready_to_generate=true when CURRENT COLLECTED STATE explicitly shows:
  purpose ✓  destination ✓  dates ✓  budget ✓  group.adults ✓  pace ✓
  Never set ready_to_generate=true based on memory or what the user said — only on CURRENT STATE.

CHIPS GUIDANCE — suggest 2-4 context-appropriate chips (never suggest "Generate itinerary"):
- purpose chips: "Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Solo Backpacking 🎒"
- pace chips: "Relaxed 😌", "Moderate ⚖️", "Packed 🏃"
- budget chips: "₹50,000", "₹1,00,000", "₹2,50,000", "₹5,00,000"
- duration chips: "3 days", "5 days", "7 days", "10 days", "2 weeks"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT — output ONLY this raw JSON object every turn. No prose before or after. No ```fences.
{{
  "reply": "Your 1-2 sentence message (markdown ok: **bold**, emoji)",
  "chips": ["Chip A", "Chip B"],
  "config_patch": {{}},
  "ready_to_generate": false,
  "summary": null
}}

When ready_to_generate=true, summary must be a single line like:
  "7 days in Bali, Indonesia · ₹80,000 · 2 adults · Relaxed honeymoon 🌴"

FIELD SHAPES — use exactly these:
- purpose: "leisure" | "adventure" | "honeymoon" | "family_vacation" | "business_leisure" | "solo_backpacking" | "group_holiday"
- destination: {{"city": "Bali", "country": "Indonesia", "lat": 0, "lon": 0}}
- destination_mode: "fixed" | "exploring" | "country"
- destination_country: "India"
- dates: {{"start": "2026-08-01", "end": "2026-08-08", "flexible": false}}
       OR {{"start": null, "end": null, "flexible": true, "duration_days": 7}}
- budget: {{"amount": 80000, "currency": "INR"}}
- group: {{"adults": 2, "kids": [], "seniors": 0, "infants": 0, "pets": 0}}
- pace: "relaxed" | "moderate" | "packed"
- origin: {{"city": "Mumbai", "iata": "", "lat": 0, "lon": 0}}
- themes: ["culture", "food"]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRELOADED DESTINATION: {preloaded_destination}

CURRENT COLLECTED STATE:
{collected_state}
"""

# ── Required field check ──────────────────────────────────────────────────────

_REQUIRED_KEYS = {
    "purpose",
    "destination_or_mode",  # checked specially below
    "dates",
    "budget",
    "group_adults",
    "pace",
}


def _has_all_required(config: dict[str, Any]) -> bool:
    """Server-side guard: verify all required fields are truly present."""
    if not config.get("purpose"):
        return False

    # Destination: either a fixed destination or a mode other than "fixed"
    dest = config.get("destination")
    mode = config.get("destination_mode", "fixed")
    if mode == "fixed" and not (dest and dest.get("city")):
        return False
    if mode == "country" and not config.get("destination_country"):
        return False

    # Dates: either start+end or flexible with duration
    dates = config.get("dates", {})
    has_dates = bool(dates.get("start") and dates.get("end")) or bool(
        dates.get("flexible") and dates.get("duration_days")
    )
    if not has_dates:
        return False

    if not (config.get("budget", {}).get("amount", 0) > 0):
        return False

    if not (config.get("group", {}).get("adults", 0) >= 1):
        return False

    if not config.get("pace"):
        return False

    return True


def _summarise_state(config: dict[str, Any]) -> str:
    """Human-readable summary of what has been collected so far."""
    lines = []

    if config.get("purpose"):
        lines.append(f"purpose: {config['purpose']}")

    dest = config.get("destination")
    mode = config.get("destination_mode", "fixed")
    if mode == "exploring":
        lines.append("destination: exploring mode (Anya will recommend)")
    elif mode == "country":
        lines.append(f"destination: exploring {config.get('destination_country', '?')}")
    elif dest and dest.get("city"):
        lines.append(f"destination: {dest['city']}, {dest.get('country', '')}")

    dates = config.get("dates", {})
    if dates.get("start") and dates.get("end"):
        lines.append(f"dates: {dates['start']} → {dates['end']}")
    elif dates.get("flexible") and dates.get("duration_days"):
        lines.append(f"dates: flexible, {dates['duration_days']} days")

    budget = config.get("budget", {})
    if budget.get("amount", 0) > 0:
        lines.append(f"budget: ₹{budget['amount']:,.0f}")

    group = config.get("group", {})
    if group.get("adults", 0) >= 1:
        parts = [f"{group['adults']} adults"]
        if group.get("kids"):
            parts.append(f"{len(group['kids'])} kids")
        if group.get("seniors", 0) > 0:
            parts.append(f"{group['seniors']} seniors")
        lines.append(f"group: {', '.join(parts)}")

    if config.get("pace"):
        lines.append(f"pace: {config['pace']}")

    if config.get("origin", {}).get("city"):
        lines.append(f"origin: {config['origin']['city']}")
    if config.get("themes"):
        lines.append(f"themes: {', '.join(config['themes'])}")

    # Signal to LLM whether the "anything else?" checkpoint has already been asked
    if config.get("_checkpoint_asked"):
        lines.append("status: ✅ 'anything else?' checkpoint already asked — ready to generate on user confirmation")
    elif all([
        config.get("purpose"), config.get("dates"), (config.get("budget") or {}).get("amount", 0) > 0,
        (config.get("group") or {}).get("adults", 0) >= 1, config.get("pace"),
        (config.get("destination_mode", "fixed") != "fixed" or (config.get("destination") or {}).get("city"))
    ]):
        lines.append("status: ⚡ all 6 required fields collected — ask 'anything else?' checkpoint next")

    return "\n".join(lines) if lines else "Nothing collected yet — this is the first message."


# ── Main chain function ───────────────────────────────────────────────────────

async def wizard_chat(request: WizardChatRequest) -> WizardChatResponse:
    if settings.llm_provider == "mock":
        return _mock_wizard(request)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        return _mock_wizard(request)

    if not settings.gemini_api_key:
        return _mock_wizard(request)

    client = google_genai.Client(api_key=settings.gemini_api_key)

    system_prompt = WIZARD_SYSTEM_PROMPT.format(
        preloaded_destination=request.preloaded_destination or "None",
        collected_state=_summarise_state(request.partial_config),
    )

    # Last 20 messages as conversation history
    history = request.messages[-20:]

    # Bootstrap: Gemini requires at least one user message
    if not history:
        seed = (
            f"I want to plan a trip to {request.preloaded_destination}."
            if request.preloaded_destination
            else "Hi, I'd like to plan a trip."
        )
        history = [type("M", (), {"role": "user", "content": seed})()]

    contents = []
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append(
            genai_types.Content(role=role, parts=[genai_types.Part(text=msg.content)])
        )

    def _call_sync() -> str:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.6,
                max_output_tokens=1024,
            ),
        )
        return response.text or ""

    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, _call_sync)
    except Exception as exc:
        # Gemini API error (quota, safety, network) — fall back to mock
        import logging
        logging.getLogger(__name__).warning("Gemini API error in wizard_chat: %s", exc)
        return _mock_wizard(request)

    try:
        import re as _re
        cleaned = raw.strip()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        # Use regex to extract the inner content reliably
        fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # If Gemini still prepended prose, grab the outermost { ... } JSON block
        json_match = _re.search(r'\{[\s\S]*\}', cleaned)
        if json_match:
            cleaned = json_match.group(0)

        data = json.loads(cleaned)

        # Merge config_patch into partial_config to check completeness
        merged = {**request.partial_config}
        patch = data.get("config_patch", {})
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v

        # Server-side override: only allow ready=true if all required fields present
        ready = data.get("ready_to_generate", False) and _has_all_required(merged)

        return WizardChatResponse(
            reply=data.get("reply", raw),
            chips=data.get("chips", []),
            config_patch=patch,
            ready_to_generate=ready,
            summary=data.get("summary") if ready else None,
        )
    except Exception:
        return WizardChatResponse(reply=raw, chips=[], config_patch={}, ready_to_generate=False)


# ── Mock fallback ─────────────────────────────────────────────────────────────

def _mock_wizard(request: WizardChatRequest) -> WizardChatResponse:
    if not request.messages or request.messages[-1].role != "user":
        return WizardChatResponse(
            reply="Hi! I'm Anya ✈️ I'll help you plan your perfect trip. What's the main purpose of this trip?",
            chips=["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧"],
        )
    return WizardChatResponse(
        reply="Got it! Tell me more — where are you thinking of going?",
        chips=["Suggest me!", "I have a destination in mind"],
        config_patch={},
        ready_to_generate=False,
    )
