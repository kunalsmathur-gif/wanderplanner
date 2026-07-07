"""Anya wizard chat chain — collects TripConfig fields through natural conversation."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel

from core.config import settings
from core.llm_client import track_gemini_usage
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
    # True when `chips` represents a multi-value field (e.g. travel themes)
    # that the user should be able to pick several of before continuing,
    # rather than a single-choice field where any click submits immediately.
    # Computed deterministically server-side (see `_is_multi_select_chips`)
    # instead of relying on the frontend guessing from free-text chip labels.
    multi_select: bool = False


# Keywords that identify a multi-value field's chip options (themes today;
# extend this list if other multi-select fields grow chip UIs later).
_MULTI_SELECT_CHIP_KEYWORDS = [
    "culture", "nature", "food", "adventure", "shopping", "photography",
    "nightlife", "sports", "wellness", "religious", "vegetarian",
]


def _is_multi_select_chips(chips: list[str]) -> bool:
    """True if every chip looks like a travel-theme option, meaning the user
    should be able to select several before continuing."""
    if len(chips) < 2:
        return False
    return all(
        any(keyword in chip.lower() for keyword in _MULTI_SELECT_CHIP_KEYWORDS)
        for chip in chips
    )


# ── System prompt ─────────────────────────────────────────────────────────────

WIZARD_SYSTEM_PROMPT = """\
# SYSTEM PURPOSE
You are Anya — a warm, experienced Indian travel planner speaking directly with a customer
over chat or voice. Your job is to understand what kind of trip they want and, once you have
enough information, hand off to the itinerary system.

You are NOT a chatbot describing its own logic. You are a travel professional.
A real travel planner never says "I need to update your budget field" or "the next missing
field is group" — they just ask the next natural question.

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

## 1a. ABSOLUTE SPEAKING RULES — READ THIS BEFORE EVERY REPLY

You are on a call with a customer. Everything in `reply` is spoken out loud to them.

NEVER mention — even once — any of the following in `reply`:
  • Field names or system terms: purpose, destination_mode, config_patch, CURRENT_STATE,
    group_adults, pace, slot, missing field, required field, schema, JSON, parameter,
    checkpoint, Stage 2, Stage 3, status.
  • Internal reasoning: "I need to parse...", "The next field is...", "I will now ask...",
    "I need to collect...", "I'll update...", "This means the destination_mode...",
    "All 6 required fields are now filled...", "The next step is to trigger...",
    "The user has just confirmed..."
  • Any sentence that describes what YOU are doing internally.

A real travel planner never narrates their own notepad. They just ask the next question.

  ✗ WRONG: "4,00,000. I need to parse this and update the `budget` field in `config_patch`.
            The next missing field is `group`. Got it, that's 4 lakh!"
  ✓ RIGHT: "Got it, a budget of 4 lakh — lovely! And who will be joining you on this trip?"

  ✗ WRONG: "All 6 required fields are now filled. The next step is to trigger the checkpoint.
            Wonderful, a relaxed pace it is!"
  ✓ RIGHT: "Wonderful, a relaxed pace it is! Anything special you'd like to add?"

  ✗ WRONG: "The 6 core fields are purpose, destination, dates, budget, group, and pace.
            I need to start collecting these. Hello! What's the purpose of your trip?"
  ✓ RIGHT: "Hello! I'm Anya, your travel planner. What kind of trip are you dreaming of?"

NEVER embed chip options inside the `reply` text. Chips go ONLY in the `chips` JSON array.

  ✗ WRONG reply: "...would you prefer relaxed, moderate, or packed? {{"Relaxed 🧘", "Moderate 🚶", "Packed 🏃"}}"
  ✓ RIGHT reply: "...would you prefer a relaxed pace, moderate, or packed?"
    RIGHT chips:  ["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"]

  ✗ WRONG reply: "What kind of trip — Leisure 🌴, Adventure 🏔️, Honeymoon 💑, or Family Vacation 👨‍👩‍👧?"
  ✓ RIGHT reply: "What kind of trip are you dreaming of?"
    RIGHT chips:  ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧"]

If you notice yourself writing internal reasoning, STOP and DELETE it before continuing.

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
    ALWAYS include chips when asking about purpose: ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"]

  Field 2 -- destination (JSON keys: "destination" OR "destination_mode" + "destination_country"; optionally "hops")
    Where they want to go.
    Case A -- specific city/place:
      destination: {{"city": "Bali", "country": "Indonesia", "lat": 0, "lon": 0}}
      destination_mode: "fixed"
    Case B -- flexible within a country:
      destination_mode: "country"
      destination_country: "Thailand"
    Case C -- open to AI suggestions:
      destination_mode: "exploring"
    Case D -- MULTIPLE specific cities/places named explicitly (multi-city / multi-hop trip):
      When the user lists 2+ specific place names (not a whole country) — e.g. "Colombo,
      Mirissa, and Yala National Park" or "Paris then Amsterdam" — put the FIRST place in
      "destination" and ALL remaining places (in the order given) in "hops". Never drop any
      named place; every place the user mentions must appear in either destination or hops.
      destination_mode: "fixed"
      destination: {{"city": "Colombo", "country": "Sri Lanka", "lat": 0, "lon": 0}}
      hops: [
        {{"city": "Mirissa", "country": "Sri Lanka", "lat": 0, "lon": 0}},
        {{"city": "Yala National Park", "country": "Sri Lanka", "lat": 0, "lon": 0}}
      ]
      This applies any time the user updates the destination too — e.g. "actually add Kandy
      as well" -> append {{"city": "Kandy", ...}} to the existing hops in config_patch.
    Map: "suggest me" / "not sure" / "anywhere" / "kuch bhi" / "you decide" -> Case C

    COUNTRY DESTINATIONS: If the user names a country (not a specific city), warmly name
    the key cities/regions you plan to explore and ask if they have a preference or are happy
    to visit all. For example:
      User: "Sri Lanka" -> "Sri Lanka is stunning! I'm thinking we cover Colombo, Kandy,
        and Galle — a beautiful mix of coast, culture, and hill country. Does that work,
        or would you prefer to focus on one region?"
      User: "Japan" -> "Japan has so much to offer! Are you thinking Tokyo and Kyoto,
        or would you like to explore further — Osaka, Hiroshima, maybe Kyushu?"

    CRITICAL — always resolve to concrete cities: "destination_mode": "country" is ONLY a
    momentary placeholder for the single turn where you first ask which cities to cover.
    The instant you name specific cities (in the very same reply — proposing them, not
    waiting for confirmation) OR the user confirms/picks cities, you MUST immediately
    switch to Case D/A in that SAME config_patch: set destination_mode: "fixed", destination
    = the first named city, and hops = the rest, using country: "<the country the user named>"
    for every one of them. Never leave a trip sitting at destination_mode "country" with no
    concrete destination — the app cannot show budget, map, or travel-tips widgets without a
    real city. Example — user says "Italy" and you reply proposing Rome, Florence, Venice:
      config_patch: {{
        "destination_mode": "fixed",
        "destination": {{"city": "Rome", "country": "Italy", "lat": 0, "lon": 0}},
        "hops": [
          {{"city": "Florence", "country": "Italy", "lat": 0, "lon": 0}},
          {{"city": "Venice", "country": "Italy", "lat": 0, "lon": 0}}
        ]
      }}
    If the user later narrows it down to just one of those cities, replace destination with
    that city and clear hops to [].

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
    kids array = list of integer ages (plain integers, e.g. [3, 6]).

  Field 6 -- pace (JSON key: "pace")
    Travel intensity. Valid values: "relaxed" | "moderate" | "packed"
    Mappings:
      "chill" / "araam se" / "no rush" / "slow" / "easy" -> relaxed
      "normal" / "balanced" -> moderate
      "hectic" / "see everything" / "lots of sightseeing" / "fast-paced" -> packed
    Chip mappings: "Relaxed 🧘" -> "relaxed" | "Moderate 🚶" -> "moderate" | "Packed 🏃" -> "packed"
    ALWAYS include chips when asking about pace: ["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"]

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
       "I'm ready" / "regenerate" / "update it" / "update my itinerary" / "regenerate as-is" /
       clicks "Just generate it!" or "Regenerate as-is" / provides optional preferences.
  When setting ready_to_generate: true, also set summary to a single human-readable line.

GUARD: If user asks to generate but fields are missing -> refuse warmly, name exactly which
fields are missing, ask for them in one combined question. Set ready_to_generate: false.

---

## 8. EXTRACTION AND CONFIG_PATCH RULES
config_patch is the ONLY mechanism by which the application records values.
  - EVERY field you extract from the user's message MUST appear in config_patch.
  - If the user provides a value, it goes in config_patch. No exceptions.
  - Extract ALL fields mentioned in a single message simultaneously.
  - config_patch must never be empty {{}} when the user just gave you new information.
  - Do not re-include fields already in CURRENT_STATE if the user did NOT change them.

NOTE: Conversation history shows previous model responses with their config_patch values.
Use these as context. Always populate config_patch with every new value the user provides
in the CURRENT message. Do not re-include fields already in CURRENT_STATE.

EXAMPLES — follow this exact pattern:

  User: "November 2026, 5 days"
  → config_patch MUST be: {{"dates": {{"start": "2026-11-01", "end": "2026-11-30", "flexible": true, "duration_days": 5}}}}

  User: "INR 3 lakhs"
  → config_patch MUST be: {{"budget": {{"amount": 300000, "currency": "INR"}}}}

  User: "two adults and a 3 year old toddler"
  → config_patch MUST be: {{"group": {{"adults": 2, "kids": [3], "seniors": 0, "infants": 0, "pets": 0}}}}

  User: "relaxed pace"
  → config_patch MUST be: {{"pace": "relaxed"}}

  User: "leisure trip"
  → config_patch MUST be: {{"purpose": "leisure"}}

---

## 9. OUTPUT SCHEMA
Respond ONLY with a valid JSON object on every turn.
No text before or after. No markdown fences. No triple backticks.
No trailing commas. No comments inside the JSON.

CRITICAL: The entire JSON response must fit in ONE short message.
  - `reply` must be 1-3 short sentences MAXIMUM. No lists, no headers, no elaboration.
  - Never write a travel guide or long description. You are on a phone call — be brief.
  - Total JSON output must be under 200 words.

Example response when user says "November 2026, 5 days":
{{
  "reply": "Got it, November 2026 for 5 days! And what kind of budget are you working with?",
  "chips": [],
  "config_patch": {{"dates": {{"start": "2026-11-01", "end": "2026-11-30", "flexible": true, "duration_days": 5}}}},
  "ready_to_generate": false,
  "summary": null
}}

Example response when user says "INR 3 lakhs":
{{
  "reply": "Understood, 3 lakh budget — great! And who will be joining you on this trip?",
  "chips": [],
  "config_patch": {{"budget": {{"amount": 300000, "currency": "INR"}}}},
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
        hops = config.get("hops") or []
        if hops:
            hop_names = ", ".join(h.get("city", "") for h in hops if h.get("city"))
            lines.append(f"destination: {dest['city']}, {dest.get('country', '')} (multi-city, additional stops: {hop_names})")
        else:
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


def _strip_leaked_schema_tail(text: str) -> str:
    """Strip a leaked copy of our own JSON schema keys from the end of the
    reply text.

    Occasionally Gemini emits *valid* JSON overall, but glitches while
    writing the `reply` string value: it echoes the remaining schema keys
    (chips/config_patch/ready_to_generate/summary) — properly escaped —
    as literal trailing text inside the string itself, e.g.:
      'Certainly! ...adventure?", "chips": [], "config_patch": {}, ...'
    `json.loads` parses this fine (the quotes are escaped), so the
    truncation/validity checks upstream never catch it. Cut the reply off
    at the first sign of a leaked schema key.
    """
    import re as _re

    tail_re = _re.compile(
        r'"?\s*,?\s*"(?:chips|config_patch|ready_to_generate|summary|reply|assistant_reply|suggested_chips)"\s*:',
        _re.IGNORECASE,
    )
    m = tail_re.search(text)
    if m:
        return text[: m.start()].rstrip().rstrip('",').rstrip()
    return text


def _strip_leaked_reasoning(text: str) -> str:
    """Strip any reasoning the LLM prepended to the reply field.

    Strategy: reasoning always ends at a sentence boundary; the real reply
    always starts with a warm/conversational opener. We scan the whole text
    for that boundary — no guard based on what the reasoning looks like,
    because reasoning can take any form.

    Two passes:
      1. Find the earliest warm opener that follows a sentence boundary and is
         preceded by content — that prefix is the leaked reasoning, discard it.
      2. If no warm opener exists, strip leading sentences that contain
         technical reasoning markers (field names, internal-state references).
    """
    import re as _re

    # Warm openers Anya uses to begin her user-facing sentences.
    # Lookbehind requires a sentence-end char; \s* allows zero-space joins like "trip.Got it".
    _WARM = (
        r'Perfect|Wonderful|Great|Got it|Sure|Absolutely|Awesome|Lovely|'
        r'Noted|Sounds good|Alright|Of course|Happy to|Hello|Hi\b|Namaste|'
        r'Welcome|Fantastic|Certainly|Excellent|Beautiful|Amazing|Superb|'
        r'Splendid|Brilliant|Delightful|Yes\b'
    )
    warm_re = _re.compile(r'(?<=[.!?])\s*(?:' + _WARM + r')', _re.IGNORECASE)

    m = warm_re.search(text)
    if m and m.start() > 0:
        # There is content before the warm opener — that content is reasoning.
        return text[m.start():].strip()

    # Pass 2: strip leading sentences that contain internal reasoning markers.
    # A sentence is reasoning if it references field names, state objects, or
    # uses internal analysis phrases — regardless of how it starts.
    _REASONING_BODY = _re.compile(
        r'config_patch|destination_mode|CURRENT_STATE|missing field|required fields?\b'
        r'|all \d+ (?:required|fields)\b'        # "All 6 required fields are now filled"
        r'|The next step\b'                       # "The next step is to trigger..."
        r'|\bcheckpoint\b'                        # "ask the checkpoint question"
        r'|The user has\b'                        # "The user has just confirmed..."
        r'|The system\b'                          # "The system has already marked..."
        r'|The prompt\b'                          # "The prompt states that..."
        r'|Since I\b'                             # "Since I cannot literally..."
        r'|I should\b'                            # "I should confirm..." / "I should not ask..."
        r'|I need to (?:parse|ask|collect|update|check|set|trigger)'
        r'|I will (?:ask|now|set|update|extract|trigger)'
        r'|I\'ll (?:ask|now|set|update|extract|begin|trigger)'
        r'|The next (?:missing )?field'
        r'|`[a-z_: -]+`'                         # any backtick-quoted identifier/value
        r'|\bslot.fill',
        _re.IGNORECASE,
    )
    _SENTENCE = _re.compile(r'^[^.!?]*[.!?]\s*')
    for _ in range(20):
        sm = _SENTENCE.match(text)
        if not sm:
            break
        sentence = sm.group(0)
        if _REASONING_BODY.search(sentence):
            text = text[sm.end():].strip()
        else:
            break  # First non-reasoning sentence — stop here

    return text.strip() or text


def _strip_trailing_json_artifacts(text: str) -> str:
    """Remove stray JSON syntax left over when a truncated/malformed LLM
    response is displayed on a best-effort basis (e.g. a leaked `",` or a
    dangling `}` / `]` from a cut-off JSON string value)."""
    import re as _re

    if not text:
        return text
    cleaned = _re.sub(r'\s*["\',\]\}]+\s*$', '', text.rstrip())
    return cleaned.rstrip() or text


def _looks_like_valid_json(raw: str) -> bool:
    """Best-effort check that Gemini's raw text is a complete, parseable
    JSON object with a non-empty `reply` field — used to decide whether a
    response was truncated by the token cap and should be retried instead
    of shown to the user as-is."""
    import re as _re

    if not raw:
        return False
    cleaned = raw.strip()
    fence_match = _re.search(r'```(?:json)?\s*([\s\S]*?)```', cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    json_match = _re.search(r'\{[\s\S]*\}', cleaned)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    reply = data.get("reply") or data.get("assistant_reply")
    return bool(reply and reply.strip())


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
        if msg.role == "user":
            contents.append(
                genai_types.Content(role="user", parts=[genai_types.Part(text=msg.content)])
            )
        else:
            # Wrap assistant messages as JSON so Gemini sees the expected output format.
            # Guard: if msg.content is itself raw JSON (from a previous leak), unwrap it.
            reply_content = msg.content
            if reply_content and reply_content.strip().startswith("{"):
                try:
                    leaked = json.loads(reply_content)
                    if isinstance(leaked, dict) and leaked.get("reply"):
                        reply_content = leaked["reply"]
                except Exception:
                    pass
            # Use the real config_patch from this turn if available — this is critical:
            # showing real patches in history teaches the LLM to populate config_patch.
            real_patch = msg.config_patch if msg.config_patch else {}
            model_json = json.dumps({
                "reply": reply_content,
                "chips": [],
                "config_patch": real_patch,
                "ready_to_generate": False,
                "summary": None,
            })
            contents.append(
                genai_types.Content(role="model", parts=[genai_types.Part(text=model_json)])
            )

    def _call_sync():
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.4,
                max_output_tokens=2048,
            ),
        )

    import logging, time
    _log = logging.getLogger(__name__)

    # Retry up to 3 times on transient API errors (503, rate limit, timeout)
    # AND on malformed/truncated JSON responses — a response that arrives
    # successfully but fails to parse is just as much a "try again" signal
    # as a network hiccup, otherwise a truncated reply gets shown verbatim.
    raw = ""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, _call_sync)
            track_gemini_usage(response, model=settings.gemini_model, purpose="wizard_chat")
            raw = response.text or ""
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            # Only retry on transient errors
            if any(code in err_str for code in ("503", "429", "UNAVAILABLE", "quota", "timeout")):
                wait = 1.5 * (attempt + 1)
                _log.warning("Gemini transient error (attempt %d/3): %s — retrying in %.1fs", attempt + 1, exc, wait)
                await asyncio.sleep(wait)
                continue
            else:
                break  # Non-retryable error — give up immediately

        # Response arrived — check it actually parses as valid JSON before
        # accepting it. If not (truncated mid-generation), retry the call
        # rather than falling straight to best-effort text extraction.
        if _looks_like_valid_json(raw):
            last_exc = None
            break
        last_exc = ValueError("Gemini response was not valid/complete JSON")
        if attempt < 2:
            _log.warning("Gemini JSON parse check failed (attempt %d/3) — retrying", attempt + 1)
            await asyncio.sleep(0.5)

    if last_exc is not None and not raw:
        _log.warning("Gemini API failed after retries: %s", last_exc)
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
            or ""  # Never fall back to raw JSON — use empty string and let strip handle it
        )
        # If reply_text itself looks like JSON (double-wrapped), try to unwrap it
        if reply_text and reply_text.strip().startswith("{"):
            try:
                inner = json.loads(reply_text)
                if isinstance(inner, dict) and inner.get("reply"):
                    reply_text = inner["reply"]
            except Exception:
                pass
        chips_list = (
            data.get("chips")
            or data.get("suggested_chips")
            or []
        )

        # Strip chips embedded inline in reply_text and recover them into chips_list
        import re as _re3

        def _extract_inline_chips(text: str, existing: list) -> tuple[str, list]:
            """Remove chip lists embedded in text; return (cleaned_text, chips)."""
            # Pattern 1: Chips: ["A", "B"] or Options: ["A", "B"]
            m = _re3.search(r'\s*(?:Chips?|Options?|chip\s*options?):\s*(\[[\s\S]*?\])', text, flags=_re3.IGNORECASE)
            if m:
                try:
                    parsed = json.loads(m.group(1))
                    if isinstance(parsed, list):
                        existing = existing or [str(c) for c in parsed]
                except Exception:
                    pass
                text = text[:m.start()].strip()

            # Pattern 2: {"Relaxed 🧘", "Moderate 🚶", ...} — Python-set-like inline chips
            m2 = _re3.search(r'\s*\{("[\s\S]+?"(?:\s*,\s*"[\s\S]+?")+)\}\s*$', text)
            if m2:
                try:
                    parsed2 = json.loads('[' + m2.group(1) + ']')
                    if isinstance(parsed2, list):
                        existing = existing or [str(c) for c in parsed2]
                except Exception:
                    pass
                text = text[:m2.start()].strip()

            return text, existing

        reply_text, chips_list = _extract_inline_chips(reply_text, chips_list)

        # Safety net: strip any reasoning the LLM leaked into the reply field
        reply_text = _strip_leaked_reasoning(reply_text)
        # Safety net: strip a leaked copy of our own schema keys from the tail
        reply_text = _strip_leaked_schema_tail(reply_text)

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

        # Safety net: the very first turn always asks about trip purpose (system
        # prompt Section 4, Field 1 mandates chips here), but with almost no
        # conversation context yet, the LLM occasionally omits them. Since this
        # is the single highest-traffic touchpoint (every user's first message),
        # deterministically backfill the standard purpose chips rather than
        # leaving the opening question chip-less.
        if not chips_list and not merged.get("purpose") and len(request.messages) <= 1:
            chips_list = ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"]

        return WizardChatResponse(
            reply=reply_text,
            chips=chips_list,
            config_patch=patch,
            ready_to_generate=ready,
            summary=data.get("summary") if ready else None,
            multi_select=_is_multi_select_chips(chips_list),
        )
    except Exception:
        # JSON parse failed — LLM returned plain text (no JSON).
        import re as _re_fb
        clean_raw = raw or ""
        extracted_chips: list[str] = []

        # Pattern 1: Chips: ["A", "B"]
        chips_match = _re_fb.search(r'\s*(?:Chips?|Options?|chip\s*options?):\s*(\[[\s\S]*?\])', clean_raw, flags=_re_fb.IGNORECASE)
        if chips_match:
            try:
                parsed = json.loads(chips_match.group(1))
                if isinstance(parsed, list):
                    extracted_chips = [str(c) for c in parsed]
            except Exception:
                pass
            clean_raw = clean_raw[:chips_match.start()].strip()

        # Pattern 2: {"Relaxed 🧘", "Moderate 🚶", ...} curly-brace set notation
        chips_match2 = _re_fb.search(r'\s*\{("[\s\S]+?"(?:\s*,\s*"[\s\S]+?")+)\}\s*$', clean_raw)
        if chips_match2 and not extracted_chips:
            try:
                parsed2 = json.loads('[' + chips_match2.group(1) + ']')
                if isinstance(parsed2, list):
                    extracted_chips = [str(c) for c in parsed2]
            except Exception:
                pass
            clean_raw = clean_raw[:chips_match2.start()].strip()

        clean_raw = _strip_leaked_reasoning(clean_raw)
        clean_raw = _strip_leaked_schema_tail(clean_raw)
        # Guard: if clean_raw still looks like raw JSON, try to extract reply from it
        if clean_raw and clean_raw.strip().startswith("{"):
            try:
                inner = json.loads(clean_raw)
                if isinstance(inner, dict) and inner.get("reply"):
                    clean_raw = inner["reply"]
                elif isinstance(inner, dict):
                    clean_raw = ""
            except Exception:
                clean_raw = ""  # Do not display raw JSON to user

        # Final safety net: strip any stray trailing JSON syntax (e.g. a
        # leaked `",` or dangling `}`/`]`) from a truncated response before
        # ever showing it to the user.
        clean_raw = _strip_trailing_json_artifacts(clean_raw)
        return WizardChatResponse(
            reply=clean_raw or "I'm on it! Just a moment…",
            chips=extracted_chips,
            config_patch={},
            ready_to_generate=False,
            multi_select=_is_multi_select_chips(extracted_chips),
        )


# ── Mock fallback ─────────────────────────────────────────────────────────────

def _mock_wizard(request: WizardChatRequest) -> WizardChatResponse:
    """Context-aware fallback when Gemini is unavailable. Uses partial_config to ask the next missing field."""
    config = request.partial_config

    if not request.messages or request.messages[-1].role != "user":
        return WizardChatResponse(
            reply="Hi! I'm Anya ✈️ I'll help you plan your perfect trip. What's the main purpose of this trip?",
            chips=["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧"],
        )

    # Ask for next missing field in order
    if not config.get("purpose"):
        return WizardChatResponse(
            reply="What kind of trip are you dreaming of?",
            chips=["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"],
            config_patch={}, ready_to_generate=False,
        )
    mode = config.get("destination_mode", "fixed")
    has_dest = (mode == "exploring") or (mode == "country" and config.get("destination_country")) or (mode == "fixed" and (config.get("destination") or {}).get("city"))
    if not has_dest:
        return WizardChatResponse(
            reply="Where are you thinking of going?",
            chips=["Suggest me! 🌍", "I have a destination in mind"],
            config_patch={}, ready_to_generate=False,
        )
    dates = config.get("dates", {})
    if not (dates.get("start") and dates.get("end")):
        return WizardChatResponse(reply="When are you planning to travel, and for how many days?", chips=[], config_patch={}, ready_to_generate=False)
    if not (config.get("budget", {}).get("amount", 0) > 0):
        return WizardChatResponse(reply="What's your approximate budget for this trip?", chips=[], config_patch={}, ready_to_generate=False)
    if not (config.get("group", {}).get("adults", 0) >= 1):
        return WizardChatResponse(reply="Who will be joining you — travelling solo, as a couple, or with family?", chips=["Solo 🧳", "Couple ❤️", "Family 👨‍👩‍👧", "Friends 🎉"], config_patch={}, ready_to_generate=False)
    if not config.get("pace"):
        return WizardChatResponse(reply="What pace works for you?", chips=["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"], config_patch={}, ready_to_generate=False)

    return WizardChatResponse(
        reply="I'm having a little trouble right now — please try again in a moment.",
        chips=[], config_patch={}, ready_to_generate=False,
    )
