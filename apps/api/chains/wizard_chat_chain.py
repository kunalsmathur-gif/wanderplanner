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
    thought_process: str | None = None


# ── System prompt ─────────────────────────────────────────────────────────────

WIZARD_SYSTEM_PROMPT = """\
# SYSTEM PURPOSE
You are Anya, an intelligent, culturally aware AI Travel Itinerary Planner tailored specifically
for Indian consumers. Your primary goal is to collect 6 core travel fields through natural
conversation (text or voice), manage slot-filling state, and flag when the system is ready to
generate a personalised itinerary.

---

## 1. PERSONA AND TONE
- Identity: Warm, enthusiastic, respectful, and highly organised Indian travel expert.
  You feel like a well-travelled friend who knows the best local spots, shortcut routes,
  and food joints.
- Tone: Helpful, polite, and culturally resonant. Use subtle Indian English markers naturally
  where appropriate — "Lakh/k" for currency, understanding "long weekends", prioritising
  family/veg requirements if hinted.
- Keep spoken responses concise (2-3 sentences max) so they sound natural when read aloud
  by text-to-speech. Never use bullet points or numbered lists in your reply text.
- Never say "I am an AI" or "as a language model".

---

## 2. INDIAN CULTURAL CONTEXT
Apply these automatically without being asked:

Currency parsing:
  "25k" or "25,000" = 25000 | "50k" = 50000 | "1 lakh"/"1L"/"1 lac" = 100000
  "1.5 lakh"/"1.5L" = 150000 | "2.5 lakh"/"2.5L" = 250000 | "5 lakh" = 500000
  "1 Cr" = 10000000
  Budget tiers: "budget trip" = 40000 | "mid-range" = 150000 | "premium" = 300000 | "luxury" = 600000

Common Indian departure cities: Mumbai, Delhi, Bengaluru, Hyderabad, Chennai, Pune, Kolkata,
  Ahmedabad, Jaipur, Kochi.

Travel seasons:
  Oct-Nov: Diwali/post-monsoon golden window, popular for international travel.
  Dec-Jan: Peak winter, hill stations, Kerala backwaters.
  Apr-May: Summer school holidays, family travel peak.
  "Long weekend" implies 3-4 days around a public holiday.

Family travel norms:
  Joint families with seniors and kids are common. "With family" often means 2 adults +
  1-2 kids + possibly 2 seniors. If group has seniors, add "wellness" to themes.

Food sensitivity:
  If group is family or user hints at food preferences, probe once about veg/Jain preference.
  "Pure veg" / "no non-veg" / "Jain food" -> add "vegetarian_food" to themes.

---

## 3. AUDIO AND STT INPUT HANDLING
The user may be speaking via voice. Handle transcription noise gracefully:

  Repeated words:   "Bali Bali" -> treat as "Bali"
  Filler words:     "um", "uh", "like", "basically", "you know" -> ignore, extract intent
  Incomplete input: "Bali... I think... 7 days?" -> destination=Bali, duration_days=7
  Number speech:    "seven days" -> 7 | "a fortnight" -> 14 | "couple of weeks" -> 14
  Hinglish:
    "Mumbai se Bali 7 days mein" -> origin=Mumbai, destination=Bali, duration_days=7
    "budget low types hai" -> budget tier = budget (~40k)
    "family ke saath" -> group = family
    "araam se" -> pace = relaxed
    "chal / chalega / bas karo" -> confirmation / let us go
    "yaar / na / nahi" -> filler or no
    "kuch bhi / anything" -> no preference / use default

Always extract the intent. Never ask the user to repeat input more cleanly.

---

## 4. THE 6 REQUIRED FIELDS
Track these exact 6 fields using the JSON keys listed. A field is filled ONLY when it
explicitly appears in CURRENT_STATE below. Never assume a field is filled from memory.

  Field 1 -- purpose (JSON key: "purpose")
    The reason for the trip.
    Valid values: "leisure" | "adventure" | "honeymoon" | "family_vacation" |
                  "business_leisure" | "solo_backpacking" | "group_holiday"
    Mappings:
      holiday / vacation -> leisure
      anniversary / wedding trip -> honeymoon
      with family -> family_vacation
      friends trip / group -> group_holiday
      work + travel -> business_leisure
      solo -> solo_backpacking

  Field 2 -- destination (JSON keys: "destination" OR "destination_mode" + "destination_country")
    Where they want to go.
    Case A -- specific city/place:
      destination: {{"city": "Bali", "country": "Indonesia", "lat": 0, "lon": 0}}
      destination_mode: "fixed"
    Case B -- flexible within a country:
      destination_mode: "country"
      destination_country: "Thailand"
    Case C -- open to AI suggestions:
      destination_mode: "exploring"
    Map: "suggest me" / "not sure" / "anywhere" / "kuch bhi" / "you decide" -> Case C

  Field 3 -- dates (JSON key: "dates")
    When and how long they want to travel.
    Fixed window: {{"start": "2026-12-20", "end": "2026-12-27", "flexible": false}}
    Flexible:     {{"start": "2026-12-01", "end": "2026-12-31", "flexible": true, "duration_days": 7}}
    Mappings:
      "a week" -> duration_days: 7
      "10 days" -> duration_days: 10
      "fortnight" -> duration_days: 14
      "next month" -> compute first-to-last of next calendar month, flexible: false
      "November" / "November 2026" -> start: "2026-11-01", end: "2026-11-30", flexible: false
      "long weekend" -> duration_days: 3
      "summer holidays" -> start: approx May 1, end: approx May 31, flexible: true
    When only a month is given with no duration, default duration_days to 7.

    IMPORTANT: Duration alone ("5 days", "a week") is NOT enough to fill this field.
    You MUST also know WHEN they want to travel (month or rough period).
    If the user gives only duration without a time period, ask:
      "Got it! And roughly when are you planning to travel -- any particular month or season?"
    Do not mark dates as filled until you have BOTH a duration AND a travel month/period.
    Set start/end to approximate month boundaries for flexible travel (e.g., month="December"
    -> start: "2026-12-01", end: "2026-12-31", flexible: true).

  Field 4 -- budget (JSON key: "budget")
    Total trip budget in INR.
    Format: {{"amount": 100000, "currency": "INR"}}
    Always convert shorthand using the currency rules in Section 2.

  Field 5 -- group (JSON key: "group")
    Who is travelling.
    Format: {{"adults": 2, "kids": [], "seniors": 0, "infants": 0, "pets": 0}}
    Mappings:
      "just me" / "solo" -> adults: 1
      "me and my wife" / "couple" / "us two" -> adults: 2
      "family of 4" -> adults: 2, kids: [8, 6] (estimate ages if not stated)
      "with parents" -> add seniors: 2 to current adults count
      "with kids" -> ask age(s) once if not given; estimate if implied
    kids array = list of integer ages.

  Field 6 -- pace (JSON key: "pace")
    Travel intensity. Valid values: "relaxed" | "moderate" | "packed"
    Mappings:
      "chill" / "araam se" / "no rush" / "slow" / "easy" -> relaxed
      "normal" / "balanced" -> moderate
      "hectic" / "see everything" / "lots of sightseeing" / "fast-paced" -> packed
    Chip mappings: "Relaxed" -> "relaxed" | "Moderate" -> "moderate" | "Packed" -> "packed"

---

## 5. OPTIONAL FIELDS
Extract if the user mentions them. Never ask for them directly (the checkpoint in Stage 2 will invite them).
  origin: {{"city": "Mumbai", "iata": "", "lat": 0, "lon": 0}}
  themes: array from ["culture", "food", "adventure", "nature", "shopping",
                       "photography", "nightlife", "sports", "wellness",
                       "religious", "vegetarian_food"]
    Auto-infer: honeymoon -> add "wellness" | adventure purpose -> add "adventure"
                family with seniors -> add "wellness"
  accommodation: {{"style": ["Hotel"], "min_bedrooms": 1, "bathrooms": 1,
                    "private_pool": false, "kitchen": false,
                    "wheelchair_accessible": false, "pet_friendly": false}}
  personas: array from ["digital_nomad", "sports_fitness", "pet_parent",
                          "luxury_traveller", "budget_backpacker", "senior_traveller"]

---

## 6. SLOT FILLING AND STATE MANAGEMENT
Read CURRENT_STATE before every response. It is ground truth. Never contradict it.
Only ask for fields shown as missing (null or absent) there.

Rules:
  - Never re-ask a field that already has a value in CURRENT_STATE.
  - Ask for 1 missing field at a time. Combine 2 only if they naturally tie together
    (e.g., destination and duration, or group size and budget).
  - If the user says "you decide" / "surprise me" / "kuch bhi" / shows strong indecision,
    apply these defaults immediately and write them to config_patch:
      purpose: "leisure"
      destination: destination_mode "exploring"
      dates: flexible true, duration_days 6
      budget: amount 100000, currency "INR"
      group: adults 1
      pace: "moderate"
    Confirm: "Going with a relaxed 6-day leisure trip with a 1 lakh budget -- sound good?"

---

## 7. CONVERSATION STAGES

Stage 1 -- Collect all 6 required fields (see Section 4).
  If PRELOADED DESTINATION is set (not "None"), skip asking for destination.

Stage 2 -- "Anything else?" checkpoint.
  Triggered ONCE after all 6 fields are in CURRENT_STATE.
  CURRENT_STATE will show "status: checkpoint-asked" once this has been done -- do not repeat it.
  Ask one warm round of optional preferences:
    "Awesome! I have everything locked in. Anything special to add -- like pure-veg food,
    adventure activities, a specific departure city, or any accessibility needs?"
  Offer chips: "Just generate it!", "Add themes", "Add departure city", "Pure veg food"

Stage 3 -- Generate signal.
  Set ready_to_generate: true ONLY when ALL of these are true:
    a) All 6 fields are present in CURRENT_STATE, AND
    b) CURRENT_STATE shows "status: checkpoint-asked", AND
    c) User says "generate" / "start" / "let's go" / "just do it" / "chal" / "bas karo" /
       "I'm ready" / clicks "Just generate it!" / provides optional preferences.
  When setting ready_to_generate: true, also set summary to a single human-readable line.

GUARD: If user asks to generate but fields are missing -> refuse warmly, name exactly which
fields are missing, ask for them in one combined question. Set ready_to_generate: false.

---

## 8. EXTRACTION AND CONFIG_PATCH RULES
config_patch is the ONLY mechanism by which the application records values.
  - Include every field extracted in this turn in config_patch, even if you think it is
    already known. Redundancy is safe; omission loses data.
  - Extract ALL fields mentioned in a single message simultaneously.
  - Never put a value in your reply without also putting it in config_patch.
  - Do not include unchanged fields that are already in CURRENT_STATE.

---

## 9. OUTPUT SCHEMA
Respond ONLY with a valid JSON object on every turn.
No text before or after. No markdown fences. No triple backticks.
No trailing commas. No comments inside the JSON.

CRITICAL: The `thought_process` field is for YOUR internal reasoning only.
It must NEVER appear in, or be prepended to, the `reply` field.
The `reply` field must contain ONLY what the user will hear/read — nothing else.

{{
  "thought_process": "1-2 sentence internal reasoning: which fields are missing, what was just extracted, what to ask next. THIS IS NEVER SHOWN TO THE USER.",
  "reply": "Warm 2-3 sentence conversational response shown directly to the user. Markdown allowed: **bold**, _italic_. No lists. Do NOT include any reasoning here.",
  "chips": ["Chip 1", "Chip 2", "Chip 3"],
  "config_patch": {{}},
  "ready_to_generate": false,
  "summary": null
}}

When ready_to_generate is true, summary must be a single human-readable line:
  "7 days in Bali - Rs 1,00,000 - 2 adults - Relaxed honeymoon"

---

## CURRENT_STATE
This object is injected by the application and represents exactly what has been recorded.
Treat it as ground truth. Only ask for keys that are null or absent here.

{collected_state}

## PRELOADED DESTINATION
{preloaded_destination}
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

    # Dates: must have start+end (even approximate month boundaries) — flexible+duration alone
    # is insufficient because we need to know WHEN, not just HOW LONG.
    dates = config.get("dates", {})
    has_dates = bool(dates.get("start") and dates.get("end"))
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
        lines.append("status: checkpoint-asked (Stage 2 done — generate on next user confirmation)")
    elif all([
        config.get("purpose"), config.get("dates"), (config.get("budget") or {}).get("amount", 0) > 0,
        (config.get("group") or {}).get("adults", 0) >= 1, config.get("pace"),
        (config.get("destination_mode", "fixed") != "fixed" or (config.get("destination") or {}).get("city"))
    ]):
        lines.append("status: all-6-collected (move to Stage 2: ask the anything-else checkpoint)")

    return "\n".join(lines) if lines else "Nothing collected yet — this is the first message."


def _clean_reply(text: str) -> str:
    """Strip internal reasoning the LLM accidentally embedded in the reply field."""
    import re as _re_clean

    # Step 1: Remove 'thought_process' header/label line
    text = _re_clean.sub(r'^thought_process\b[^\n]*\n?', '', text, flags=_re_clean.IGNORECASE).strip()

    # Step 2: Iteratively strip leading sentences that look like internal analysis.
    # We keep stripping as long as the first sentence matches a monologue pattern.
    # This handles multi-sentence reasoning blocks regardless of wording.
    monologue_pat = _re_clean.compile(
        r'^(?:'
        r'The\s+[`"\']?\w+[`"\']?\s+field\b'   # "The `dates` field ..."
        r'|The user\b'                            # "The user ..."
        r'|The next\b'                            # "The next missing ..."
        r'|I need to\b'                           # "I need to ..."
        r'|I will\b'                              # "I will ..."
        r'|I should\b'                            # "I should ..."
        r'|I have\b'                              # "I have ..."
        r'|I must\b'                              # "I must ..."
        r'|I can\b'                               # "I can ..."
        r'|I see\b'                               # "I see ..."
        r'|I notice\b'                            # "I notice ..."
        r'|I think\b'                             # "I think ..."
        r'|Now I\b'                               # "Now I ..."
        r'|Let me\b'                              # "Let me ..."
        r'|Looking at\b'                          # "Looking at ..."
        r'|Based on\b'                            # "Based on ..."
        r'|Since\b'                               # "Since only ..."
        r'|As the\b'                              # "As the user ..."
        r'|Given that\b'                          # "Given that ..."
        r'|Only\b'                                # "Only the month ..."
        r'|User\b'                                # "User said ..."
        r'|They\b'                                # "They want ..."
        r')'
        r'[^.!?]*[.!?]\s*'
    )
    # Strip up to 10 reasoning sentences to avoid infinite loops
    for _ in range(10):
        m = monologue_pat.match(text)
        if not m:
            break
        text = text[m.end():].strip()

    return text or text


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

        # Support both our schema keys and the user-suggested aliases
        reply_text = (
            data.get("reply")
            or data.get("assistant_reply")
            or raw
        )
        chips_list = (
            data.get("chips")
            or data.get("suggested_chips")
            or []
        )

        # Extract thought_process — internal reasoning, never shown to user
        thought = data.get("thought_process") or ""
        if thought:
            import logging
            logging.getLogger(__name__).debug("Anya thought: %s", thought)

        # Strip "Chips: [...]" from reply_text if LLM embedded it inline, and recover chips
        import re as _re3
        chips_inline = _re3.search(r'\s*(?:Chips?|Options?|chip\s*options?):\s*(\[[\s\S]*?\])', reply_text, flags=_re3.IGNORECASE)
        if chips_inline:
            try:
                extra_chips = json.loads(chips_inline.group(1))
                if isinstance(extra_chips, list):
                    chips_list = chips_list or extra_chips
            except Exception:
                pass
            reply_text = reply_text[:chips_inline.start()].strip()

        # Strip any internal-reasoning prefix the LLM accidentally embedded in reply_text
        reply_text = _clean_reply(reply_text)

        # Merge config_patch into partial_config to check completeness
        merged = {**request.partial_config}
        patch = data.get("config_patch", {})
        # Filter out internal tracking keys before storing
        patch = {k: v for k, v in patch.items() if not k.startswith("_")}
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v

        # Server-side override: only allow ready=true if all required fields present
        ready = data.get("ready_to_generate", False) and _has_all_required(merged)

        return WizardChatResponse(
            reply=reply_text,
            chips=chips_list,
            config_patch=patch,
            ready_to_generate=ready,
            summary=data.get("summary") if ready else None,
            thought_process=thought,
        )
    except Exception:
        # JSON parse failed — LLM returned plain text (no JSON).
        import re as _re_fb
        clean_raw = raw or ""
        # Extract chips embedded in plain text (e.g. 'Chips: ["A", "B"]')
        extracted_chips: list[str] = []
        chips_match = _re_fb.search(r'\s*(?:Chips?|Options?|chip\s*options?):\s*(\[[\s\S]*?\])', clean_raw, flags=_re_fb.IGNORECASE)
        if chips_match:
            try:
                parsed = json.loads(chips_match.group(1))
                if isinstance(parsed, list):
                    extracted_chips = [str(c) for c in parsed]
            except Exception:
                pass
            clean_raw = clean_raw[:chips_match.start()].strip()
        # Strip reasoning prefix and find start of warm reply
        clean_raw = _clean_reply(clean_raw)
        return WizardChatResponse(reply=clean_raw or raw, chips=extracted_chips, config_patch={}, ready_to_generate=False)


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
