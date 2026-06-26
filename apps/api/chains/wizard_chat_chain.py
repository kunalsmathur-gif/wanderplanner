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
Your job: collect trip planning details through natural conversation, then signal when ready to generate the itinerary.

PERSONALITY:
- Speak like a knowledgeable friend, not a form or a bot.
- Keep replies to 1-2 sentences max (then offer chips for quick replies).
- Show genuine excitement about the destination or travel style.
- Indian context: understand rupees (₹), Indian cities as origins, typical Indian travel budgets and habits.
- Never ask for a field that is already collected (see CURRENT STATE below).

REQUIRED FIELDS — collect all 6 before setting ready_to_generate=true:
1. purpose          — reason for travel
2. destination      — city+country, OR destination_mode="exploring", OR destination_mode="country"+destination_country
3. dates            — start+end dates, OR duration_days+flexible=true
4. budget.amount    — total INR budget (number)
5. group.adults     — number of adults (≥1)
6. pace             — relaxed / moderate / packed

OPTIONAL — weave in naturally if user mentions them:
- origin.city           — departure city (helps with flight cost estimates)
- group.kids            — ages of children 2–8 yrs
- group.seniors         — count of seniors 60+
- group.infants         — count of infants 0–2
- themes                — culture / food / adventure / nature / shopping / photography / nightlife / sports
- accommodation.style   — Hotel / Airbnb / Hostel / Resort / Service Apartment
- personas              — digital_nomad / sports_fitness / pet_parent / budget_backpacker / luxury_traveller

SMART EXTRACTION RULES:
- "just me and my wife" → group: {{adults: 2, kids: [], seniors: 0, infants: 0, pets: 0}}
- "₹1.5 lakh" or "1.5 lakhs" → budget: {{amount: 150000, currency: "INR"}}
- "a week" → dates: {{start: null, end: null, flexible: true, duration_days: 7}}
- "next month" → compute approximate start/end dates (first to last day of next calendar month)
- "suggest me" / "not sure" / "anywhere" → destination_mode: "exploring"
- "India trip" / "exploring France" → destination_mode: "country", destination_country: "India"/"France"
- Purpose synonyms: "holiday"→"leisure", "anniversary"→"honeymoon", "with family"→"family_vacation"
- Combine multiple fields from one message when possible.

CONVERSATION FLOW:
- If preloaded_destination is set, skip asking about destination — jump to purpose.
- Suggested order: purpose → destination → dates → budget → group → pace → optional fields.
- You may combine two short questions: "How many people, and what's your rough budget?"
- Once all 6 required fields are collected: give a warm confirmation summary, set ready_to_generate=true.

CHIPS GUIDANCE — suggest 2–4 context-appropriate chips:
- purpose chips: "Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Solo Backpacking 🎒"
- pace chips: "Relaxed 😌", "Moderate ⚖️", "Packed 🏃"
- budget chips: "₹50,000", "₹1,00,000", "₹2,50,000", "₹5,00,000"
- duration chips: "3 days", "5 days", "7 days", "10 days", "2 weeks"

RESPONSE FORMAT — respond ONLY with raw JSON (no prose, no markdown fences, no explanation before or after), every single turn:
{{
  "reply": "Your message (markdown ok: **bold**, _italic_, emoji)",
  "chips": ["Chip A", "Chip B"],
  "config_patch": {{
    // Only the fields extracted from the user's latest message.
    // Use exact TripConfig field shapes (see FIELD SHAPES).
    // Empty {{}} if nothing new was extracted.
  }},
  "ready_to_generate": false,
  "summary": null
}}

CRITICAL: Output ONLY the JSON object. Do not write anything before or after the JSON. Do not use ```json fences.

FIELD SHAPES (use exactly these structures):
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
- accommodation: {{"style": ["Hotel"], "min_bedrooms": 1, "bathrooms": 1, "private_pool": false, "kitchen": false, "wheelchair_accessible": false, "pet_friendly": false}}
- personas: ["digital_nomad"]

When ready_to_generate=true, set summary to a single line, e.g.:
"7 days in Bali, Indonesia · ₹80,000 · 2 adults · Moderate pace 🌴"

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
        # Strip markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[-1] if cleaned.count("```") >= 2 else cleaned
            cleaned = cleaned.lstrip("json").strip().rstrip("`").strip()

        # If Gemini prepended prose, find the first { ... } JSON block
        import re as _re
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
