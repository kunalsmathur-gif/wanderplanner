"""Anya wizard chat chain — collects TripConfig fields through natural conversation."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from core.budget_estimator import absolute_budget_floor_check, budget_estimate_prompt_hint
from core.chips import (
    GENERIC_CHIP_KEYWORDS,
    MULTI_SELECT_CHIP_KEYWORDS,
    is_multi_select_chips,
)
from core.config import settings
from core.currency_convert import TOP_10_CURRENCIES, currency_conversion_prompt_hint
from core.keyword_match import has_keyword
from core.llm_client import track_gemini_usage
from core.validation import (
    MAX_CHAT_HISTORY,
    MAX_CITY_LEN,
    MAX_TRIP_CONTEXT_CHARS,
    normalise_choice_fields,
    text_validator,
)
from models.chat import ChatMessage
from services.geocode import geocode_city

logger = logging.getLogger(__name__)

_validate_preloaded_destination = text_validator(
    max_length=MAX_CITY_LEN, field="preloaded_destination", require_alphanumeric=True
)


class WizardChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list, max_length=MAX_CHAT_HISTORY)
    partial_config: dict[str, Any] = {}
    preloaded_destination: str | None = None  # e.g. "Bali, Indonesia"

    @field_validator('preloaded_destination', mode='before')
    @classmethod
    def clean_preloaded_destination(cls, v: Any) -> Any:
        return None if v is None else _validate_preloaded_destination(v)

    @field_validator('partial_config')
    @classmethod
    def bound_partial_config(cls, v: dict[str, Any]) -> dict[str, Any]:
        """The whole partial config is serialised into the wizard prompt, so
        it is bounded by serialised size like `ChatRequest.trip_context` — it
        arrives as a loose dict (a partially-filled TripConfig), so per-field
        types can't be applied to it here."""
        serialised = json.dumps(v, default=str)
        if len(serialised) > MAX_TRIP_CONTEXT_CHARS:
            raise ValueError(
                f"partial_config must serialise to at most {MAX_TRIP_CONTEXT_CHARS} characters "
                f"(received {len(serialised)})"
            )
        return v


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
    # Short-lived HMAC of `reply` (core/reply_signing.py), set by the router
    # rather than here so this chain stays provider-agnostic. `/voice/tts`
    # requires this to match before it will speak the text — without it, TTS
    # would be a free public speech-synthesis API anyone could farm against
    # the monthly character budget (docs/adr/0001-anya-voice-provider.md).
    reply_sig: str | None = None


# Chip classification moved to `core/chips.py` in v10.61 so `chat_refine_chain`
# can share it rather than growing a second copy. Re-exported here under the
# original private names purely so existing call sites and tests keep working;
# new code should import from `core.chips` directly.
_MULTI_SELECT_CHIP_KEYWORDS = MULTI_SELECT_CHIP_KEYWORDS
_GENERIC_CHIP_KEYWORDS = GENERIC_CHIP_KEYWORDS
_is_multi_select_chips = is_multi_select_chips


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
  ✓ RIGHT: "Got it, a budget of 4 lakh — lovely! I have everything I need now, anything special
            you'd like to add before I put your itinerary together?"

  ✗ WRONG: "All 6 required fields are now filled. The next step is to trigger the checkpoint.
            Wonderful, a relaxed pace it is!"
  ✓ RIGHT: "Wonderful, a relaxed pace it is! What's your approximate budget in ₹ (INR)?"

  ✗ WRONG: "The 6 core fields are purpose, destination, dates, group, pace, and budget.
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

## 3a. REPLY LANGUAGE — MIRROR THE USER, BUT ONLY IN `reply`

Answer in the language and script the user is using. They may switch at any turn; follow them.

  User writes/speaks Devanagari Hindi ("मुझे गोवा जाना है")  -> reply in Devanagari Hindi.
  User writes Hinglish in Roman script ("Goa jaana hai yaar") -> reply in Roman-script Hinglish.
  User writes English                                          -> reply in English.
  Mixed in one message -> follow the script of the majority of their words.

Your persona does not change with the language. You are the same warm Indian travel planner;
keep replies to 2-3 sentences so they read naturally aloud.

⚠️ THIS APPLIES TO `reply` ONLY. `chips` and `config_patch` are consumed by code, not read by
the user, and both break if translated:

  • `chips` — ALWAYS English, exactly as specified in section 4, emoji included. The app
    classifies chip groups by matching English words, so a translated chip silently changes
    how the group behaves rather than failing visibly.

  • `config_patch` — ALWAYS English, Latin script, for every value. Place names especially:
    a destination is a database key that is geocoded, ingested and cached under its English
    name, so "गोवा" and "Goa" become two unrelated destinations and the Hindi one starts a
    whole redundant ingestion of data we already hold.

  ✗ WRONG: reply: "बिल्कुल! गोवा के लिए कब जाना चाहेंगे?"
           chips: ["आराम से 🧘", "मध्यम 🚶"]
           config_patch: {{"destination": {{"city": "गोवा", "country": "भारत"}}}}

  ✓ RIGHT: reply: "बिल्कुल! गोवा के लिए कब जाना चाहेंगे?"
           chips: ["Relaxed 🧘", "Moderate 🚶"]
           config_patch: {{"destination": {{"city": "Goa", "country": "India"}}}}

So a Hindi turn is Hindi prose wrapped around English data. That asymmetry is deliberate.

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

    CRITICAL — never strand a trip in "exploring" mode while collecting other fields.
    A budget can't be estimated and dates/group questions feel pointless if the user doesn't
    even know where they're going yet. So the moment destination_mode becomes "exploring",
    treat naming actual places as the URGENT next step — prioritize it over dates, budget,
    or group size:
      - If you already know the purpose (or any other stated preference — beaches, culture,
        nightlife, kid-friendly, budget level, etc.), propose 2-3 concrete destinations with a
        one-line reason for each IN THAT SAME REPLY, and ask the user to pick one (or say
        "you choose"). Do NOT ask about dates/budget/group in this reply.
      - If you don't yet know the purpose either, ask for purpose AND make clear a destination
        suggestion is coming right after — do not silently move past destination toward budget
        or group size while it is still unresolved.
      - Once the user picks a place (or says "you choose"/"surprise me"), immediately set
        destination_mode: "fixed" with that destination in config_patch that same turn, THEN
        continue collecting the remaining fields (dates, group, pace, budget).
      - Never leave destination_mode: "exploring" set for more than the single turn where you
        first ask about destination preferences — the very next assistant turn must either name
        concrete candidates or lock in the chosen one.

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

  Field 4 -- group (JSON key: "group")
    Who is travelling.
    Format: {{"adults": 2, "kids": [], "seniors": 0, "infants": 0, "pets": 0}}
    Mappings:
      "just me" / "solo" -> adults: 1
      "me and my wife" / "couple" / "us two" -> adults: 2
      "family of 4" -> adults: 2, kids: [8, 6] (estimate ages if not stated)
      "with parents" -> add seniors: 2 to current adults count
      "with kids" -> ask age(s) once if not given; estimate if implied
    kids array = list of integer ages (plain integers, e.g. [3, 6]).

  Field 5 -- pace (JSON key: "pace")
    Travel intensity. Valid values: "relaxed" | "moderate" | "packed"
    Mappings:
      "chill" / "araam se" / "no rush" / "slow" / "easy" -> relaxed
      "normal" / "balanced" -> moderate
      "hectic" / "see everything" / "lots of sightseeing" / "fast-paced" -> packed
    Chip mappings: "Relaxed 🧘" -> "relaxed" | "Moderate 🚶" -> "moderate" | "Packed 🏃" -> "packed"
    ALWAYS include chips when asking about pace: ["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"]

  Field 6 -- budget (JSON key: "budget")
    Total trip budget in INR. **INR (₹) is always the canonical/stored currency — say so explicitly the
    first time you ask for budget**, e.g. "What's your approximate budget in ₹ (INR)? If you'd rather
    tell me in USD, EUR, GBP, AED, SGD, AUD, CAD, JPY, THB, or CHF, that's fine too — I'll convert it."
    Format: {{"amount": 100000, "currency": "INR"}}
    Always convert shorthand using the currency rules in Section 2.

    This is the LAST field asked, and it's asked AFTER the Stage 2 "anything else?" checkpoint
    (see Section 7) — by the time you reach it, group, pace, AND every optional preference the
    user chose to share (themes, veg/Jain preference, departure city, splurge/save categories,
    prebooked costs) are already known. Do not defer or jump the field order for it.
    A user CAN still volunteer a budget number early (unprompted in their opening message, or in
    reply to a different question) — ALWAYS record whatever figure they give you into
    config_patch.budget the instant they state it (per Section 8: extract every field mentioned,
    regardless of what you asked), even though the checkpoint/other fields haven't happened yet.

    🔴 DO NOT JUDGE FEASIBILITY YOURSELF. Never estimate, compare, or comment on whether a stated
    budget is enough or too low — even if the user directly asks "is ₹50,000 feasible for this?"
    or asks to lower a previously-mentioned figure. That used to be your job via a rough heuristic,
    but the app now runs a real, accurate cost check (grounded in live flight/stay/entry-cost data)
    on its own — you never quote your own numbers. Saying your own (less accurate) opinion on the
    number first would show the user two different, possibly conflicting figures. Just warmly
    acknowledge the number and record it. What you say next depends on WHEN the budget arrived:
      - If group, dates, and destination are ALL already known (the normal case — budget is the
        last field): tell them you're having it checked against real costs right now (no numbers
        of your own) — e.g. "Got it, ₹3,00,000 — let me check that against real costs for you."
        Do NOT ask "are you ready to generate?" or claim anything about generation status this
        turn; the app takes it from here (see Section 7, Stage 3).
      - If the budget arrived EARLY/OUT OF ORDER (volunteered before group/dates/destination are
        all known): say so explicitly instead of implying a check is happening right now — e.g.
        "Got it, ₹3,00,000 — noted! I can't properly check that against real costs until I know
        [whichever of destination/dates/group is still missing], so let's fill those in first and
        I'll check it for you once we're there." This sets an honest expectation instead of
        silently moving on, which can otherwise make the user think no check is coming at all.
        (Note: a separate, instant, non-negotiable sanity check runs automatically server-side the
        moment ANY budget figure is recorded — completely independent of this rule and of whatever
        you say. If that check fails, it silently REPLACES your reply for that turn with its own
        hard warning and keeps the budget field unset until the user restates it, regardless of
        field order. You don't need to do anything for this — just follow the rule above as normal.)

    FOREIGN CURRENCY STATED BY THE USER (e.g. "$2000", "1500 euros", "AED 5000"):
      Never do this conversion math yourself — it is computed deterministically server-side.
      Check {currency_conversion_hint} below: if it is non-empty, it already contains the exact
      converted INR figure — use that exact number for config_patch.budget.amount (currency always
      "INR"), and mention BOTH the original stated amount and the converted ₹ figure + rate in your
      reply for transparency (e.g. "Got it, $2000 is about ₹1,73,000 at today's rate."). If a currency
      is mentioned that ISN'T one of the 10 supported ones above, tell the user you currently only
      support INR + those 10 currencies and ask them to restate in one of those (or in ₹).

    RECOMMENDING A BUDGET (user asks you to suggest/recommend one instead of giving their own number
    — a different situation from feasibility-checking a number the user already gave; this is just
    a rough, quick, in-conversation estimate to help someone with no idea where to start):
      Never invent a number yourself and never use the Section 2 "Budget tiers" shorthand table for this —
      that table is only for parsing the user's OWN stated amount (e.g. "a budget trip" -> 40000), not for
      generating a recommendation.
      Follow {budget_estimate_hint} below exactly:
        - If it tells you group size is unknown (can happen if the user asks for a recommendation
          before group size is known), ask for group composition FIRST and do NOT quote any number
          until you have it.
        - Once it gives you a computed estimate, present it in your own words, ALWAYS stating both the
          TOTAL and the PER-PERSON figure, and mention it covers flights + stay + food as a bare minimum
          (activities/shopping/local transport are extra) — and that the app will double-check it
          against real costs once they confirm a number. Briefly mention any flagged assumptions
          (trip length, comfort level, season) so the user can correct them.
        - Do NOT set config_patch.budget yet when you first present this recommended figure (or when
          the user asks a follow-up like "give me a breakup/breakdown of that") — it is only a proposal,
          not yet the user's confirmed budget. Setting config_patch.budget here marks the budget field as
          done, which incorrectly advances the wizard past the last required field underneath a reply
          that is still just discussing/confirming the budget — a jarring mismatch for the user.
          Only set config_patch.budget once the user actually accepts a figure (e.g. "sounds good",
          "yes", "let's go with that", or a specific number of their own) — until then, keep asking
          "Does that work for you?" (or similar) with no chips, exactly like the normal budget question.

---

## 5. OPTIONAL FIELDS
Extract if the user mentions them. Never ask for them directly (the checkpoint in Stage 2 will invite them).
  origin: {{"city": "Mumbai", "iata": "", "lat": 0, "lon": 0}}
    Exception: while RECOMMENDING A BUDGET (see below), {budget_estimate_hint} may explicitly tell you to
    ask for the departure city (flight cost depends heavily on it) — follow that instruction when it says so,
    even though origin is otherwise never asked for directly.
  themes: array from ["culture", "food", "adventure", "nature", "shopping",
                       "photography", "nightlife", "sports", "wellness",
                       "religious", "vegetarian_food"]
    Auto-infer: honeymoon -> add "wellness" | adventure purpose -> add "adventure"
                family with seniors -> add "wellness"
    CRITICAL — whenever you offer themes as a chip choice (e.g. after the user picks
    "Add themes" at the Stage 2 checkpoint, or asks to add/change themes), you MUST
    reply with chips set to EXACTLY this fixed list, in this exact wording, every time —
    do not invent destination-specific wording, do not omit or reorder any, do not add
    extras: ["Culture 🏛️", "Food 🍜", "Adventure 🏔️", "Nature 🌿", "Shopping 🛍️",
    "Photography 📸", "Nightlife 🌃", "Sports ⚽", "Wellness 🧘", "Religious 🛕",
    "Vegetarian Food 🥗", "No preference"]. This exact, fixed wording is required for the
    app's multi-select UI to work — free-form or reworded chips silently break multi-select
    and force the user back to picking just one. Map the user's selected chip(s) back to the
    enum values above (e.g. "Vegetarian Food" -> "vegetarian_food"); "No preference" -> [].
  accommodation: {{"style": ["Hotel"], "min_bedrooms": 1, "bathrooms": 1,
                    "private_pool": false, "kitchen": false,
                    "wheelchair_accessible": false, "pet_friendly": false}}
  personas: array from ["digital_nomad", "sports_fitness", "pet_parent",
                          "luxury_traveller", "budget_backpacker", "senior_traveller"]
  crowd_preference: "touristy" | "balanced" | "offbeat" (default "balanced" — only set when the user signals it)
    Mappings:
      "hidden gems" / "less crowded" / "offbeat" / "off the beaten path" / "away from tourists" /
      "local experiences" / "secret spots" / "bheed nahi chahiye" / "peaceful places" -> offbeat
      "famous spots" / "main attractions" / "iconic places" / "must-see" / "first time, want the classics" -> touristy
    Chip suggestion (offer once at the Stage 2 checkpoint, alongside other optional prefs):
      "Crowd style? 🧭" -> chips ["Iconic Spots 🗼", "Mix of Both ⚖️", "Hidden Gems 💎"]
      "Iconic Spots" -> touristy | "Mix of Both" -> balanced | "Hidden Gems" -> offbeat
  splurge_categories: array from ["accommodation", "food", "activities", "shopping", "local_transport"]
  save_categories: array from ["accommodation", "food", "activities", "shopping", "local_transport"]
    Only extract if the user explicitly says something like "splurge on hotels but keep food cheap",
    "I don't care about shopping, save there", "nice hotel is a priority", "we want to eat well but save on transport".
    Never ask for these directly — Stage 2's optional checkpoint (now asked BEFORE budget,
    see Section 7) may offer them as a one-off suggestion (see chip below), but do not block
    the required-fields flow on it. Gathering these before budget matters: they directly affect
    the real cost estimate the app's automatic feasibility check runs the instant budget is
    recorded, so knowing them upfront makes that check more accurate.
    Chip suggestion (offer once, at the Stage 2 checkpoint, alongside other optional prefs):
      "Want to splurge on anything? 💰" -> chips ["Nice Hotel 🏨", "Great Food 🍽️", "Top Activities 🎟️", "No preference"]
      A user picking "Nice Hotel" -> splurge_categories: ["accommodation"]. "No preference" -> leave both arrays empty and move on.
  prebooked_flights_inr: integer (INR) — ONLY if the user explicitly says they've already booked/paid for flights
    (e.g. "I already booked my tickets for 50k", "flights are done, cost 30000").
    ALWAYS ask for the actual amount paid rather than guessing: "Got it — how much did the flights cost in total?"
  prebooked_accommodation_inr: integer (INR) — ONLY if the user explicitly says they've already booked/paid for
    a hotel/stay (e.g. "hotel is already booked for 20k", "accommodation sorted, paid 15000").
    ALWAYS ask for the actual amount paid rather than guessing.
    These feed directly into budget recommendations and the feasibility check — once known, the real paid
    amount replaces the heuristic estimate for that cost component so the remaining-budget math is accurate.

---

## 6. SLOT FILLING AND STATE MANAGEMENT
Read CURRENT_STATE before every response. It is ground truth. Never contradict it.
Only ask for fields shown as missing (null or absent) there.

Rules:
  - Never re-ask a field that already has a value in CURRENT_STATE.
  - Ask for 1 missing field at a time. Combine 2 only if they naturally tie together
    (e.g., destination and duration, or group size and pace).
  - If the user says "you decide" / "surprise me" / "kuch bhi" / shows strong indecision,
    apply these defaults immediately and write them to config_patch:
      purpose: "leisure"
      destination: destination_mode "exploring"
      dates: flexible true, duration_days 6
      group: adults 1
      pace: "moderate"
      budget: amount 100000, currency "INR"
    Confirm: "Going with a relaxed 6-day leisure trip with a 1 lakh budget -- sound good?"

---

## 7. CONVERSATION STAGES

Stage 1 -- Collect the 5 core conversational fields (see Section 4, Fields 1-5: purpose,
  destination, dates, group, pace). Budget (Field 6) is deliberately NOT part of this stage —
  it comes later, in Stage 2.5, after the optional checkpoint below.
  If PRELOADED DESTINATION is set (not "None"), skip asking for destination.

Stage 2 -- "Anything else?" checkpoint.
  Triggered ONCE after those 5 core fields are in CURRENT_STATE (CURRENT_STATE will show
  "status: 5-core-fields-collected" right before this).
  CURRENT_STATE will show "status: checkpoint-asked..." once this has been done -- do not repeat it.
  Ask one warm round of optional preferences:
    "Awesome! Just a couple of quick preferences before we talk numbers — anything like pure-veg
    food, adventure activities, a specific departure city, or any accessibility needs?"
  Offer chips, but ONLY for optional fields CURRENT_STATE does NOT already show a value for:
    "No, let's continue!" (always -- moves straight to Stage 2.5's budget question, NEVER to
    generation: budget isn't known yet), "Add themes" (always -- themes can always be added to),
    "Add departure city" (omit if origin/departure city is already known),
    "Pure veg food" (omit if vegetarian_food is already in themes).
  Never re-offer a chip for an optional field the user has already answered -- chips should
  only repeat mid-flow inside a feasibility-adjustment or itinerary-edit exchange, not here.
  Whatever the user says (a real preference, "no thanks", or a chip tap), your VERY NEXT reply
  after this must move on to asking for budget (Stage 2.5) -- do not linger on optional prefs
  once the user has answered or declined once.

Stage 2.5 -- Budget (Field 6, see Section 4 for full rules).
  Ask for it once Stage 2's checkpoint has had its one round. This is the LAST field.
  🔴 Do not judge, estimate, or comment on whether the number is enough — see Field 6's
  "DO NOT JUDGE FEASIBILITY YOURSELF" rule. Record it and stop; the app checks it for real.

Stage 3 -- Generate signal.
  Set ready_to_generate: true ONLY on the SPECIFIC turn where budget (the last field) transitions
  from missing to present -- i.e. the same turn where the user just gave you their budget number
  and you're putting it in config_patch.budget for the first time -- assuming every other field
  and the checkpoint are already done. NO separate "shall I go ahead?" confirmation turn is
  needed; that one turn is the trigger. The app itself runs an automatic, accurate cost check
  (see Field 6) the instant it sees ready_to_generate: true, and either proceeds straight to
  generation or shows the user a real shortfall + adjustment options -- THAT is the real
  confirmation step now, so never ask your own "ready to generate?" question.
  🔴 Do NOT set ready_to_generate: true again on a LATER turn just because CURRENT_STATE still
  shows all 6 fields filled (e.g. the user asks an unrelated follow-up question, or you're mid
  checkpoint/edit exchange) -- that would silently re-trigger generation/the cost check on turns
  that have nothing to do with budget. Only two things may set ready_to_generate: true:
    (a) the budget-just-recorded turn described above, or
    (b) the user EXPLICITLY asking to (re)generate right now -- e.g. "regenerate as-is",
        "regenerate", "update it", "update my itinerary", "generate it now", "I'm ready",
        "chal"/"chalo", "bas karo" -- this is the edit-mode path, used when reopening the wizard
        on an already-complete trip (see EDIT MODE note below) or when the user asks again later.
  When setting ready_to_generate: true, also set summary to a single human-readable line.

EDIT MODE: reopening the wizard on an already-generated trip preloads CURRENT_STATE with all 6
  fields already filled and skips straight to an "anything you'd like to change?" turn -- in that
  state, do NOT set ready_to_generate: true just because the fields are complete; wait for the
  user to either change something (then treat budget-change the same as a fresh budget-just-
  recorded trigger) or explicitly ask to regenerate/update as-is (trigger (b) above).


GUARD: If user asks to generate but fields are missing -> refuse warmly, name exactly which
fields are missing (this will usually just be budget, since it's asked last), ask for them in
one combined question. Set ready_to_generate: false.

CRITICAL -- NEVER HALLUCINATE GENERATION STATUS:
  You have NO visibility into whether an itinerary has actually been generated -- only the
  application does that, as a real action taken AFTER you set ready_to_generate: true in this
  same turn, AND only once the app's own automatic feasibility check (Field 6) passes. You must
  NEVER say things like "Generating your itinerary now", "Your itinerary is ready", or answer
  "yes, it's ready" to a user asking whether it's done -- even if it feels like the natural
  conversational answer. If the user asks whether their itinerary is ready and you are not this
  turn setting ready_to_generate: true, say you can't check that from here and that the app
  screen will show progress/the result directly.
  Also double-check CURRENT_STATE literally has all 6 fields filled before ever setting
  ready_to_generate: true -- do not set it, or claim generation, based on something you merely
  mentioned/inferred in your own reply text (e.g. calling it a "family trip" in prose
  does NOT mean purpose was actually recorded -- it only counts if it's in CURRENT_STATE or in
  config_patch this turn).

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
  "reply": "Got it, November 2026 for 5 days! And who will be joining you on this trip?",
  "chips": [],
  "config_patch": {{"dates": {{"start": "2026-11-01", "end": "2026-11-30", "flexible": true, "duration_days": 5}}}},
  "ready_to_generate": false,
  "summary": null
}}

Example response when user says "INR 3 lakhs" (group and pace already known from earlier turns):
{{
  "reply": "Understood, 3 lakh budget — great! I've got everything I need. Anything special you'd like to add before I put your itinerary together?",
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

## BUDGET GUIDANCE HINT (a computed bare-minimum estimate for this trip — use it in TWO situations)
{budget_estimate_hint}

## FOREIGN CURRENCY CONVERSION HINT (only relevant if the user's latest message stated a budget in a non-INR currency)
{currency_conversion_hint}

## ENTRY / VISA CONTEXT (background only — present when the destination country has entry rules on file)
{visa_hint}
Rules for using it:
  - Only mention it if the user ASKS about visas, entry rules, or documents. Never volunteer it
    mid-wizard — the job of this conversation is to collect trip fields, not to brief the user.
  - It is community-sourced and may be out of date. Never state it as a determination ("you do not
    need a visa"). Summarise it as what the guide says, and always tell the user to confirm with the
    destination's official immigration site before booking.
  - If it says "(none on file)", say you don't have reliable entry information for that country and
    point them at the official source. Do not answer from your own knowledge — a wrong visa answer
    costs the user a trip.

## FRESHNESS CAVEAT HINT (only present when the user's latest message reads as time-sensitive)
{router_hint}
Rules for using it: if present, weave the caveat naturally into your reply (e.g. mention that
conditions can change and to double-check a live/official source closer to the trip) instead of
answering as if you have current, up-to-the-minute information. Never say this out loud as a
system disclosure like "I don't have real-time data" — just naturally hedge the specific claim.

## PRELOADED DESTINATION
{preloaded_destination}
"""


# Only asked-about visa questions trigger a lookup. Whole-word matched via
# core/keyword_match.py, not `in` — "visa" as a bare substring hits
# "Visakhapatnam", an Indian city this product will genuinely see.
_VISA_QUESTION_KEYWORDS = frozenset({
    "visa", "visas", "e-visa", "evisa", "passport", "passports",
    "entry", "immigration", "customs", "permit", "permits", "eta",
})


async def _visa_hint_for(partial_config: dict[str, Any], last_user_text: str | None) -> str:
    """Entry-rules context for the wizard prompt, or "" for "say nothing".

    🔴 **Gated on the user actually asking.** Every wizard turn is on the
    user's critical path, and an unconditional lookup would add an embedding
    plus a Qdrant round-trip to all of them to serve a question that comes up
    in a small minority of conversations. v10.47.0's measurements are the
    reason this is a gate rather than an always-on hint.

    Resolves the country from the collected config only — never from the city
    name — because a city->country lookup here would mean a geocode call on
    the same critical path, and `destination.country` is already collected by
    the wizard itself.
    """
    if not has_keyword(last_user_text or "", _VISA_QUESTION_KEYWORDS):
        return ""

    destination = partial_config.get("destination") or {}
    country = ""
    if isinstance(destination, dict):
        country = (destination.get("country") or "").strip()
    if not country:
        country = (partial_config.get("destination_country") or "").strip()
    if not country:
        return ""

    from services.visa import retrieve_visa_note
    return await retrieve_visa_note(country, last_user_text or "")


def _router_hint_for(last_user_text: str | None) -> str:
    """Freshness-caveat hint for the wizard prompt (issue #35 agentic
    router), or "" for "say nothing". Pure heuristic — no I/O, no LLM call,
    safe to run on every turn. Gated behind `agentic_router_enabled` so it
    can be turned off independently of the retrieval-path work it's a
    precursor to."""
    if not settings.agentic_router_enabled:
        return ""
    from services.query_router import route_query
    route = route_query(last_user_text)
    return route.note or ""

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


# Phrases that falsely imply generation has started/finished — used as a
# safety net to catch the LLM narrating success in `reply` text without the
# backing `ready_to_generate` flag actually being true this turn (a real
# observed failure mode: the model says "Generating your itinerary now" or
# "Yes, it's ready!" purely as conversational text, with no actual action
# behind it, leaving the user stuck with no loader/CTA and no itinerary).
_HALLUCINATED_GENERATION_RE = re.compile(
    r"\bgenerat(?:ing|ed)\b.{0,40}\b(?:itinerary|trip)\b"  # "generating"/"generated" (gerund/past — an
                                                            # in-progress-or-done claim), NOT bare "generate"
                                                            # (used in legitimate questions like "shall I
                                                            # generate your itinerary?")
    r"|\bis\s+(?:now\s+)?ready\b"      # "itinerary is (now) ready" / "it is ready" — an assertion, not the
                                        # interrogative "are you ready" (different verb form: are, not is)
    r"|\bit'?s\s+ready\b",              # "it's ready" contraction form of the same assertion
    re.IGNORECASE,
)

# Explicit user requests to (re)generate right now — the ONLY thing (besides
# the budget-just-recorded transition, checked separately in wizard_chat())
# allowed to set ready_to_generate: true on a turn where all 6 fields were
# ALREADY complete before this turn started (e.g. edit mode, or asking again
# later). Mirrors Section 7 Stage 3's trigger (b) in the system prompt.
_EXPLICIT_REGENERATE_RE = re.compile(
    r"\bregenerat\w*\b"                      # "regenerate", "regenerating", "regenerate as-is"
    r"|\bupdate\s+(?:it|my\s+itinerary)\b"    # "update it" / "update my itinerary"
    r"|\bgenerate\s+it\s+now\b"
    r"|\bjust\s+(?:do\s+it|generate\s+it)\b"
    r"|\bi'?m\s+ready\b"
    r"|\bchal(?:o|ega)?\b"
    r"|\bbas\s+karo\b",
    re.IGNORECASE,
)


# Canonical chip sets keyed by the field they belong to, used to detect a
# reply that has moved on to a later question but still carries a STALE chip
# set from an earlier, already-answered field (see _is_stale_chips below).
_FIELD_CHIP_SETS: dict[str, frozenset[str]] = {
    "purpose": frozenset({"Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"}),
    "destination": frozenset({"Suggest me! 🌍", "I have a destination in mind"}),
    "group": frozenset({"Solo 🧳", "Couple ❤️", "Family 👨‍👩‍👧", "Friends 🎉"}),
    "pace": frozenset({"Relaxed 🧘", "Moderate 🚶", "Packed 🏃"}),
}

# Purpose chip label -> canonical config value, keyed by the label with
# emoji/whitespace stripped and lowercased. Used as a deterministic fallback
# (see _infer_purpose_from_chip_tap below) for when the LLM's own reply
# clearly moves on to the next question (e.g. "Where are you dreaming of
# heading?") but omits `purpose` from config_patch — observed in the wild as
# the purpose chips reappearing under a reply that had already moved past
# purpose, because CURRENT_STATE never actually recorded it.
_PURPOSE_CHIP_VALUES: dict[str, str] = {
    "leisure": "leisure",
    "adventure": "adventure",
    "honeymoon": "honeymoon",
    "family vacation": "family vacation",
    "friends trip": "friends trip",
    "solo": "solo",
}


def _strip_emoji(text: str) -> str:
    """Removes emoji pictographs AND the invisible joiner/modifier
    codepoints used to compose multi-part emoji (e.g. the "family" emoji
    👨‍👩‍👧 is actually 👨 + ZERO WIDTH JOINER + 👩 + ZERO WIDTH JOINER + 👧).
    Stripping only the pictograph range (as this used to do) left the ZWJ
    (U+200D) characters behind — invisible on screen, but enough to make
    "family vacation" != "family vacation \u200d\u200d" in an exact-match
    dict lookup, silently breaking chip-tap detection for every purpose/
    group chip that uses a ZWJ-sequence emoji. Also strips the variation
    selector (U+FE0F) some emoji renderers append, for the same reason.
    Additionally covers U+2600-U+27BF (Misc Symbols / Dingbats) — e.g. the
    ❤️ in the "Couple ❤️" group chip lives here, outside the main pictograph
    block, and was previously left behind entirely (not just its variation
    selector)."""
    return re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27bf\u200d\ufe0f]", "", text)


def _infer_purpose_from_chip_tap(last_user_text: str | None) -> str | None:
    """Deterministically resolve a purpose value from a user message that's
    just a canonical purpose-chip tap (emoji and case aside). Returns None
    for free-form text — see _infer_purpose_from_free_text below for that."""
    if not last_user_text:
        return None
    stripped = _strip_emoji(last_user_text).strip().lower()
    return _PURPOSE_CHIP_VALUES.get(stripped)


# Word-boundary keywords for inferring purpose from a full descriptive
# sentence (e.g. "A 6 day bali family trip for 2 people") rather than a bare
# chip tap. Checked in this order — most specific first — because a couple
# of these overlap in ordinary English ("family vacation" contains
# "vacation", which would otherwise also fire the generic leisure case).
# Bug fix: the LLM occasionally omits `purpose` from config_patch even when
# the user's own sentence states it in plain words (not just a chip tap),
# leaving CURRENT_STATE never recording it — same failure shape as
# _infer_purpose_from_chip_tap's bug, but for prose instead of a tap. Once
# purpose looks "missing" for the rest of the conversation, the purpose
# chips keep reappearing under every later question (budget, budget
# adjustment, ...) because `_next_missing_field_prompt`'s fallback treats
# it as still the next thing to ask.
_PURPOSE_FREE_TEXT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("honeymoon", ["honeymoon", "newlywed", "newly wed"]),
    ("family vacation", ["family"]),
    ("friends trip", ["friends", "buddies", "girls trip", "guys trip"]),
    ("solo", ["solo trip", "solo travel", "traveling alone", "travelling alone", "by myself", "on my own"]),
    ("adventure", ["adventure", "trekking", "hiking"]),
    ("leisure", ["leisure"]),
]


def _infer_purpose_from_free_text(last_user_text: str | None) -> str | None:
    """Deterministically resolve a purpose value from a full sentence that
    states it in plain words, not just a chip tap (see
    _infer_purpose_from_chip_tap for that narrower case). Word-boundary
    matched (core/keyword_match.has_keyword) so e.g. "family" doesn't fire on
    an unrelated word containing it as a substring. Returns None if no
    keyword matches — the LLM remains responsible for anything less literal."""
    if not last_user_text:
        return None
    for value, keywords in _PURPOSE_FREE_TEXT_KEYWORDS:
        if has_keyword(last_user_text, keywords):
            return value
    return None


# Same failure shape as purpose (see above), but for pace: "Relaxed 🧘" /
# "Moderate 🚶" / "Packed 🏃" chip taps and their equivalent plain-English
# phrasing (e.g. "keep it relaxed", "a packed schedule"). Checked most
# specific first so "packed"/"relaxed" (which imply a clear preference) take
# priority over the more generic "moderate".
_PACE_CHIP_VALUES: dict[str, str] = {
    "relaxed": "relaxed",
    "moderate": "moderate",
    "packed": "packed",
}

_PACE_FREE_TEXT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("relaxed", ["relaxed", "laid back", "laid-back", "chill", "easy going", "easy-going", "slow paced", "slow-paced", "leisurely pace"]),
    ("packed", ["packed", "action packed", "action-packed", "jam packed", "jam-packed", "fast paced", "fast-paced", "hectic"]),
    ("moderate", ["moderate", "balanced pace", "medium pace"]),
]


def _infer_pace_from_chip_tap(last_user_text: str | None) -> str | None:
    """Deterministically resolve a pace value from a user message that's just
    a canonical pace-chip tap (emoji and case aside). Returns None for
    free-form text — see _infer_pace_from_free_text below for that."""
    if not last_user_text:
        return None
    stripped = _strip_emoji(last_user_text).strip().lower()
    return _PACE_CHIP_VALUES.get(stripped)


def _infer_pace_from_free_text(last_user_text: str | None) -> str | None:
    """Deterministically resolve a pace value from a full sentence that
    states it in plain words, not just a chip tap. Word-boundary matched
    (core/keyword_match.has_keyword). Returns None if no keyword matches —
    the LLM remains responsible for anything less literal."""
    if not last_user_text:
        return None
    for value, keywords in _PACE_FREE_TEXT_KEYWORDS:
        if has_keyword(last_user_text, keywords):
            return value
    return None


# Same failure shape as purpose/pace above, but for budget: the wizard prompt
# (Section 2) already teaches the LLM to convert "25k" / "1 lakh" / "3 Cr"
# shorthand into config_patch.budget.amount, but the LLM occasionally
# acknowledges the figure in its reply text and moves on without actually
# emitting it in config_patch — leaving CURRENT_STATE never recording a
# budget, which then re-triggers the budget question (and, per the bug this
# was written for, restarts the purpose-chip fallback chain) on later turns.
# Deliberately requires an explicit currency marker (₹ / rupees / rs / inr /
# lakh / crore) rather than firing on any bare number, since a plain digit in
# a sentence is far more likely to be a day count, headcount, or date than an
# unmarked rupee amount.
_INR_AMOUNT_PATTERN = re.compile(
    r"(?:₹\s*(?P<sym_amt>\d[\d,]*(?:\.\d+)?)(?:\s*(?P<sym_mult>lakhs?|lacs?|crores?|cr|k))?)"
    r"|(?:(?P<unit_amt>\d[\d,]*(?:\.\d+)?)\s*(?P<unit_mult>lakhs?|lacs?|crores?|cr)\b)"
    # word-after-number ("50000 INR", "3 lakh rupees") or word-before-number
    # ("INR 20,000", "Rs 50000") — users phrase this either way.
    r"|(?:(?P<rs_amt>\d[\d,]*(?:\.\d+)?)\s*(?P<rs_mult>k)?\s*(?:rupees?|rs\.?|inr)\b)"
    r"|(?:\b(?:rupees?|rs\.?|inr)\s*(?P<rs_amt2>\d[\d,]*(?:\.\d+)?)(?:\s*(?P<rs_mult2>lakhs?|lacs?|crores?|cr|k))?)",
    re.IGNORECASE,
)

_INR_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000,
}


def _infer_budget_amount_from_free_text(last_user_text: str | None) -> int | None:
    """Deterministically extracts an INR budget amount (e.g. "₹1.5 lakh",
    "3 lakh rupees", "2 Cr", "50000 INR") from a full sentence. Returns None
    if nothing matches an explicit rupee marker — the LLM remains
    responsible for anything less literal, and foreign-currency amounts are
    handled separately by core/currency_convert.py."""
    if not last_user_text:
        return None
    match = _INR_AMOUNT_PATTERN.search(last_user_text)
    if not match:
        return None
    amount_str = match.group("sym_amt") or match.group("unit_amt") or match.group("rs_amt") or match.group("rs_amt2")
    mult_str = (match.group("sym_mult") or match.group("unit_mult") or match.group("rs_mult") or match.group("rs_mult2") or "").lower()
    if not amount_str:
        return None
    try:
        amount = float(amount_str.replace(",", ""))
    except ValueError:
        return None
    amount *= _INR_MULTIPLIERS.get(mult_str, 1)
    return int(amount) if amount > 0 else None


# Same failure shape as purpose/pace/budget above, but for group composition.
# Bug fix (2026-08-12): this field previously had NO free-text fallback, so
# when Gemini's JSON response was malformed for the turn that answers the
# group-composition follow-up (e.g. "4 couples i.e 8 adults, and 4 kids
# (aged 8,6,3,3)"), the except-branch below fell back to
# `request.partial_config` -- which still has `adults: 0` because the client
# only applies a patch AFTER it receives one -- and `_is_stale_chips` then
# judged `group` as NOT yet filled. That let the previous turn's stale
# Solo/Couple/Family/Friends chips leak through under the reply that had
# already moved on to asking about pace (observed in prod: correct pace
# *text*, but group-type chips underneath it). Deliberately requires an
# explicit "adults" marker -- a bare number is far more likely to be a day
# count or an age -- mirroring the budget parser's explicit-currency-marker
# requirement.
_GROUP_ADULTS_PATTERN = re.compile(r"(\d+)\s*adults?\b", re.IGNORECASE)
_GROUP_SENIORS_PATTERN = re.compile(r"(\d+)\s*seniors?\b", re.IGNORECASE)
_GROUP_KID_AGES_PATTERN = re.compile(
    r"(?:kids?|children)\s*\(?\s*aged?\s*:?\s*([\d]+(?:\s*,\s*\d+)*)",
    re.IGNORECASE,
)


def _infer_group_from_free_text(last_user_text: str | None) -> dict[str, Any] | None:
    """Deterministically extracts a group-composition patch (adults,
    optionally kids/seniors) from a full sentence stating it in plain words
    (e.g. "4 couples i.e 8 adults, and 4 kids (aged 8,6,3,3)"). Returns None
    if no explicit "adults" marker is found -- the LLM remains responsible
    for anything less literal. Kid ages outside the valid 2-17 range are
    dropped rather than raising, since this is a best-effort backfill."""
    if not last_user_text:
        return None
    adults_match = _GROUP_ADULTS_PATTERN.search(last_user_text)
    if not adults_match:
        return None
    patch: dict[str, Any] = {"adults": int(adults_match.group(1))}

    seniors_match = _GROUP_SENIORS_PATTERN.search(last_user_text)
    if seniors_match:
        patch["seniors"] = int(seniors_match.group(1))

    ages_match = _GROUP_KID_AGES_PATTERN.search(last_user_text)
    if ages_match:
        ages = [int(a) for a in re.findall(r"\d+", ages_match.group(1))]
        kids = [age for age in ages if 2 <= age <= 17]
        if kids:
            patch["kids"] = [{"age": age} for age in kids]

    return patch


# Same failure shape as purpose/pace/budget/group above, but for dates. Unlike
# those fields, dates have NO canonical chip set at all (see
# _next_missing_field_prompt: the dates question returns chips=[]), so the
# specific "stale chip leaks through" symptom can't manifest here -- but the
# underlying loss is worse: if the LLM's JSON is malformed on the turn the
# user states their travel window (e.g. "November 13th to 19th"), the answer
# vanishes entirely (the except-branch falls back to the pre-patch
# request.partial_config) and the question is silently re-asked, with no
# record the user already answered it.
#
# Deliberately narrow scope: only the single most common, unambiguous shape --
# an explicit day-range within one stated month (optionally with an explicit
# year) -- either "<Month> <day> to <day>" or "<day> to <day> <Month>".
# Bare numeric date ranges (e.g. "13/11 to 19/11") are deliberately NOT
# handled, since day/month order is locale-ambiguous and a wrong guess here
# is worse than asking again. "Next month" / "a week" / "fortnight" / season
# names etc. (see Field 3 in the system prompt) are left to the LLM -- they
# require calendar math this deterministic parser isn't attempting to
# duplicate for every phrasing.
_MONTH_NAMES: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_NAMES_RE = "|".join(sorted(_MONTH_NAMES, key=len, reverse=True))

_DATE_RANGE_MONTH_FIRST_RE = re.compile(
    r"\b(?P<month>" + _MONTH_NAMES_RE + r")\.?\s+(?P<day1>\d{1,2})(?:st|nd|rd|th)?"
    r"\s*(?:to|-|–|—|through|until)\s*(?P<day2>\d{1,2})(?:st|nd|rd|th)?"
    r"(?:,?\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_RANGE_DAY_FIRST_RE = re.compile(
    r"\b(?P<day1>\d{1,2})(?:st|nd|rd|th)?"
    r"\s*(?:to|-|–|—|through|until)\s*(?:the\s*)?(?P<day2>\d{1,2})(?:st|nd|rd|th)?"
    r"\s+(?:of\s+)?(?P<month>" + _MONTH_NAMES_RE + r")\.?"
    r"(?:,?\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)


def _infer_dates_from_free_text(last_user_text: str | None, reference_date: date | None = None) -> dict[str, Any] | None:
    """Deterministically extracts a fixed {start, end, flexible: false} dates
    patch from a sentence naming an explicit day-range within one month (see
    module comment above for exactly what is and isn't handled). Returns None
    if nothing matches -- the LLM remains responsible for everything else
    (bare durations, relative periods, season names, cross-month ranges).
    `reference_date` defaults to today and exists only so tests don't depend
    on wall-clock time; when no year is stated, the nearest FUTURE occurrence
    of that month/day is assumed (a trip dated in the past makes no sense)."""
    if not last_user_text:
        return None
    if reference_date is None:
        reference_date = datetime.now(UTC).date()

    match = _DATE_RANGE_MONTH_FIRST_RE.search(last_user_text) or _DATE_RANGE_DAY_FIRST_RE.search(last_user_text)
    if not match:
        return None

    month = _MONTH_NAMES[match.group("month").lower()]
    try:
        day1 = int(match.group("day1"))
        day2 = int(match.group("day2"))
    except (TypeError, ValueError):
        return None

    year_str = match.group("year")
    if year_str:
        year = int(year_str)
    else:
        # No year stated — pick the nearest future occurrence of this
        # month/day-1 combination (this year, unless that's already past).
        year = reference_date.year
        try:
            candidate = date(year, month, day1)
        except ValueError:
            return None
        if candidate < reference_date:
            year += 1

    try:
        start = date(year, month, day1)
        end = date(year, month, day2)
    except ValueError:
        return None
    if end < start:
        return None  # e.g. "the 25th to the 3rd" spans a month boundary — not handled here

    return {"start": start.isoformat(), "end": end.isoformat(), "flexible": False}


# Same failure shape as purpose/pace/budget/group/dates above: the LLM
# occasionally acknowledges a destination stated in prose (in its reply
# text -- e.g. "Wonderful, Bali for 6 days...") without ever emitting it in
# config_patch, most often when the opening message packs several fields
# into one sentence (e.g. "bali 6 days for a family of 4 - leisure -
# 10-15th nov"). Unlike those fields, a destination is open-vocabulary (any
# place name worldwide), so it can't be matched against a closed enum --
# instead this extracts a candidate from one of a few narrow, unambiguous
# phrasings and only trusts it once Nominatim confirms it's a real place
# (see services.geocode.geocode_city). Deliberately restricted to the
# opening turn (see call sites): later turns are answers to whatever
# question is currently being asked (budget, group, pace, ...), and running
# this against every one of those would just be wasted geocoding calls with
# a real (if small) risk of a false-positive place match.
_DESTINATION_LEADING_PHRASE_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z\s]{1,40}?)\s+(?:for\s+)?\d+\s*(?:[-\u2013\u2014]|to)?\s*(?:day|days|night|nights)\b",
    re.IGNORECASE,
)
_DESTINATION_TRIP_TO_RE = re.compile(
    r"\btrip to\s+([A-Za-z][A-Za-z\s]{1,40}?)(?=[,.;!?]|\s+(?:for|with|in)\b|$)",
    re.IGNORECASE,
)
_DESTINATION_DAYS_IN_RE = re.compile(
    r"\b(?:day|days|night|nights)\s+(?:in|to)\s+([A-Za-z][A-Za-z\s]{1,40}?)(?=[,.;!?]|\s+(?:for|with)\b|$)",
    re.IGNORECASE,
)
# Candidates made up entirely of these words are never real place names --
# skip geocoding them rather than burning a Nominatim call (and risking an
# odd false-positive match) on "we want" or similar filler.
_DESTINATION_STOPWORDS = {
    "i", "we", "my", "our", "us", "a", "an", "the", "want", "wanted", "wanting",
    "looking", "planning", "plan", "need", "needed", "would", "like", "to", "for",
    "trip", "vacation", "holiday", "go", "going", "book", "booking",
}


async def _infer_destination_from_free_text(last_user_text: str | None) -> dict[str, Any] | None:
    """Deterministically extracts+geocodes a destination city from a
    compact trip-brief sentence, trying each candidate phrasing in turn and
    returning the first one Nominatim confirms is a real place. Returns None
    (never raises) on no match or an all-candidates geocoding miss/failure --
    the LLM remains responsible for every other phrasing."""
    if not last_user_text:
        return None

    candidates: list[str] = []
    for pattern in (_DESTINATION_LEADING_PHRASE_RE, _DESTINATION_TRIP_TO_RE, _DESTINATION_DAYS_IN_RE):
        match = pattern.search(last_user_text)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) >= 2 and set(candidate.lower().split()) - _DESTINATION_STOPWORDS:
                candidates.append(candidate)

    for candidate in candidates:
        try:
            result = await geocode_city(candidate)
        except Exception:
            continue
        parts = [p.strip() for p in result.display_name.split(",") if p.strip()]
        city = parts[0] if parts else candidate.title()
        country = parts[-1] if len(parts) > 1 else city
        return {"city": city, "country": country, "lat": result.lat, "lon": result.lon}

    return None


def _is_destination_mode_chip_tap(last_user_text: str | None) -> bool:
    """True when the user's last message was a tap of one of the destination
    MODE chips ("Suggest me!" / "I have a destination in mind") rather than
    an actual place name. Used to suppress those same chips from reappearing
    under the very next question — once the mode is picked, the follow-up
    ("Where are you thinking of going?" / "Could you tell me the
    destination?") expects free-form text (a city/country name), not another
    tap of the mode choice the user already made (see bug: mode chips
    re-rendered verbatim under the destination-name follow-up)."""
    if not last_user_text:
        return False
    stripped = _strip_emoji(last_user_text).strip().lower()
    canonical = {
        _strip_emoji(c).strip().lower()
        for c in _FIELD_CHIP_SETS["destination"]
    }
    return stripped in canonical


def _is_group_type_chip_tap(last_user_text: str | None) -> bool:
    """True when the user's last message was a tap of one of the group-TYPE
    chips (Solo/Couple/Family/Friends) rather than actual traveler counts.
    Tapping one of these only tells us the *category* of group, not the
    numbers — the very next question always asks for the actual composition
    ("how many adults, children (and their ages), and any seniors will be
    travelling?"), which expects free-form numbers, not another tap of the
    same type chip. Used to suppress the group chips from reappearing under
    that follow-up (see bug: group-type chips re-rendered verbatim under the
    adult/children-count follow-up, since `_is_stale_chips` only considers
    `group` "filled" once `adults` is actually set, which doesn't happen
    until this very question is answered)."""
    if not last_user_text:
        return False
    stripped = _strip_emoji(last_user_text).strip().lower()
    canonical = {
        _strip_emoji(c).strip().lower()
        for c in _FIELD_CHIP_SETS["group"]
    }
    return stripped in canonical


# Keywords identifying the one-off "which city will you be flying out of?"
# question (see budget_estimate_prompt_hint's departure-city gate). This
# question has no canonical chip set of its own — the answer is a free-form
# city name — but it fires *before* pace is known, so the generic "field is
# missing -> backfill its canonical chips" and "chips look stale" safety
# nets below both mistake it for the pace question and attach
# Relaxed/Moderate/Packed chips underneath it (see bug: pace chips shown
# under the departure-city question).
_DEPARTURE_CITY_QUESTION_KEYWORDS = frozenset({
    "departure city", "flying out of", "flying from", "fly out of",
    "fly from", "which city will you", "which airport",
})


def _is_departure_city_question(reply_text: str) -> bool:
    """True if `reply_text` is asking the user for their departure/origin
    city (the budget-estimate flight-cost gate), which takes free-form text
    and has no chips of its own."""
    return has_keyword(reply_text or "", _DEPARTURE_CITY_QUESTION_KEYWORDS)


def _filter_answered_checkpoint_chips(chips: list[str], config: dict[str, Any]) -> list[str]:
    """Drops Stage 2 "anything else?" checkpoint chips that invite the user
    to fill an optional field they've already answered (e.g. "Add departure
    city" once `origin.city` is known, "Pure veg food" once vegetarian_food
    is already in themes) -- these chips should only repeat inside a
    feasibility-adjustment or itinerary-edit exchange, never at the
    checkpoint itself. "Add themes"/"Just generate it!" always survive:
    themes are open-ended (more can always be added) and generate is the
    perpetual call-to-action, not a one-off field prompt."""
    if not chips:
        return chips
    has_origin = bool((config.get("origin") or {}).get("city"))
    has_veg = "vegetarian_food" in (config.get("themes") or [])
    kept = []
    for chip in chips:
        low = chip.lower()
        if has_origin and "departure city" in low:
            continue
        if has_veg and ("veg" in low and "food" in low):
            continue
        kept.append(chip)
    return kept


def _is_stale_chips(chips: list[str], config: dict[str, Any]) -> bool:
    """True if `chips` matches a field's canonical set but CURRENT_STATE says
    that field is already filled — i.e. the model echoed an old question's
    chips instead of the one it's actually asking now."""
    chip_set = frozenset(chips)
    dest = config.get("destination")
    mode = config.get("destination_mode", "fixed")
    filled = {
        "purpose": bool(config.get("purpose")),
        "destination": (mode == "exploring") or (mode == "country" and config.get("destination_country")) or (mode == "fixed" and dest and dest.get("city")),
        "group": (config.get("group", {}).get("adults", 0) >= 1),
        "pace": bool(config.get("pace")),
    }
    for field, canonical in _FIELD_CHIP_SETS.items():
        if chip_set == canonical and filled.get(field):
            return True
    return False


def _absolute_budget_floor_warning_text(amount: int | float, floor_estimate: dict[str, Any]) -> str:
    """Builds the hard-warning reply text once a stated `amount` has failed
    the real, destination-aware floor in `floor_estimate` (see
    core.budget_estimator.absolute_budget_floor_check)."""
    floor_total = floor_estimate["total_inr"]
    breakdown = floor_estimate["breakdown"]
    duration = floor_estimate["duration_days"]
    return (
        f"Just flagging this before we go further — ₹{amount:,.0f} doesn't look enough for this trip. "
        f"Even at the cheapest possible (economical, solo-traveller) estimate for what you've told me so far "
        f"({duration} day{'s' if duration != 1 else ''}), it works out to roughly ₹{floor_total:,} "
        f"(flights ₹{breakdown['flights_inr']:,} + stay ₹{breakdown['stay_inr']:,} + food ₹{breakdown['food_inr']:,}). "
        "Could you double-check and restate your budget? (In ₹, or another currency — I'll convert it.)"
    )


async def _absolute_budget_floor_warning(config: dict[str, Any]) -> str | None:
    """Hard, deterministic (non-LLM) sanity-floor check — see
    core.budget_estimator.absolute_budget_floor_check. Fires the INSTANT a
    budget figure is recorded, using whatever real destination/dates/group
    details are already known (never a flat generic figure): an amount that
    can't even cover the cheapest possible version of the trip described so
    far should never have to wait for the rest of the conversation — let
    alone the app's Gemini-based feasibility check at the very end — to be
    caught. Returns a warning string if the stated amount fails the floor,
    else None."""
    amount = (config.get("budget") or {}).get("amount", 0)
    if not amount or amount <= 0:
        return None
    floor_estimate = await absolute_budget_floor_check(config)
    if not floor_estimate or amount >= floor_estimate["total_inr"]:
        return None
    return _absolute_budget_floor_warning_text(amount, floor_estimate)


def _next_missing_field_prompt(config: dict[str, Any]) -> tuple[str, list[str]]:
    """Returns (reply, chips) for the next required field still missing from
    config, in field order. Used as the honest fallback whenever the model
    claims (or implies) the trip is ready/generating without the fields to
    back it up — see _HALLUCINATED_GENERATION_RE — so the user always gets a
    real next step instead of a dead-end success claim."""
    if not config.get("purpose"):
        return (
            "Just need one more thing — what's the main purpose of this trip?",
            ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"],
        )
    dest = config.get("destination")
    mode = config.get("destination_mode", "fixed")
    has_dest = (mode == "exploring") or (mode == "country" and config.get("destination_country")) or (mode == "fixed" and dest and dest.get("city"))
    if not has_dest:
        return ("Where are you thinking of going?", ["Suggest me! 🌍", "I have a destination in mind"])
    dates = config.get("dates") or {}
    if not (dates.get("start") and dates.get("end")):
        return ("When are you planning to travel, and for how many days?", [])
    if not (config.get("group", {}).get("adults", 0) >= 1):
        return ("Who will be joining you — travelling solo, as a couple, or with family?", ["Solo 🧳", "Couple ❤️", "Family 👨‍👩‍👧", "Friends 🎉"])
    if not config.get("pace"):
        return ("What pace works for you?", ["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"])
    if not (config.get("budget", {}).get("amount", 0) > 0):
        return (f"What's your approximate budget in ₹ (INR)? (Or tell me in {', '.join(TOP_10_CURRENCIES)} — I'll convert.)", [])
    # All fields are actually present — the false claim likely came from a
    # non-triggering confirmation (e.g. the checkpoint wasn't asked yet, or
    # `ready_to_generate` genuinely wasn't set this turn). Nudge forward
    # honestly rather than repeat a claim we can't back up.
    return ("Everything's noted! Want me to go ahead and generate your itinerary now?", ["Just generate it! 🚀"])


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
    elif dates.get("duration_days"):
        # Duration alone is NOT sufficient (see Field 3 rules) — a real
        # travel period (month/season -> start/end) is still required.
        # Bug fix: this used to read `dates.get("flexible") and
        # dates.get("duration_days")` and report dates as already known
        # ("flexible, N days") whenever BOTH were set, even with start/end
        # still null — exactly the shape the inspiration-card/preload flow
        # seeds (flexible: true, duration_days: N, start/end: null). The LLM
        # then believed dates were complete and silently skipped asking WHEN
        # the trip was, so it never reached ready_to_generate (which
        # correctly still requires start/end via _has_all_required),
        # leaving the user stuck with no exact dates ever asked and no
        # Generate button ever appearing. Report duration-known-but-period-
        # missing instead so the LLM asks for the remaining piece.
        lines.append(
            f"dates: duration known ({dates['duration_days']} days) but travel period "
            "(month/season) is NOT yet known — dates field is still INCOMPLETE, must ask when"
        )

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

    budget = config.get("budget", {})
    if budget.get("amount", 0) > 0:
        lines.append(f"budget: ₹{budget['amount']:,.0f}")

    if config.get("origin", {}).get("city"):
        lines.append(f"origin: {config['origin']['city']}")
    if config.get("themes"):
        lines.append(f"themes: {', '.join(config['themes'])}")

    # Signal to LLM whether the "anything else?" checkpoint has already been
    # asked. The checkpoint now fires after the 5 core conversational fields
    # (purpose/destination/dates/group/pace) — BEFORE budget — so that
    # departure city, splurge/save prefs, and any prebooked costs are known
    # before Anya ever asks for a number, and so the app's Gemini feasibility
    # check (which runs automatically the instant budget is recorded — see
    # Stage 3) has the fullest possible picture to validate against.
    if config.get("_checkpoint_asked"):
        if (config.get("budget") or {}).get("amount", 0) > 0:
            lines.append(
                "status: checkpoint-asked, budget-collected (all fields present — the app is "
                "validating this budget against real costs right now; do not ask 'ready to "
                "generate?' yourself, the app will confirm or flag a shortfall)"
            )
        else:
            lines.append("status: checkpoint-asked (Stage 2 done — ask for budget next)")
    elif all([
        config.get("purpose"),
        # Bug fix: this used to be a bare `config.get("dates")` truthiness
        # check, which passed for ANY non-empty dates dict — including the
        # preload-seeded `{start: null, end: null, flexible: true,
        # duration_days: N}` shape with no real travel period. That falsely
        # flipped this to "all-6-collected" (and could even reach
        # checkpoint-asked / ready_to_generate territory) while
        # _has_all_required() below correctly still required start/end,
        # silently desyncing the two and leaving the wizard stuck asking
        # nothing further while never actually becoming ready to generate.
        # Require the same start+end check used everywhere else so the
        # status line can never outrun the real gate.
        bool((config.get("dates") or {}).get("start") and (config.get("dates") or {}).get("end")),
        (config.get("group") or {}).get("adults", 0) >= 1, config.get("pace"),
        (config.get("destination_mode", "fixed") != "fixed" or (config.get("destination") or {}).get("city"))
    ]):
        lines.append("status: 5-core-fields-collected (move to Stage 2: ask the anything-else checkpoint, budget comes after)")

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


def _decode_stray_unicode_escapes(text: str) -> str:
    """Decode literal `\\uXXXX` JSON-style escape sequences (e.g. `\\u20b9`
    for ₹) that leak into the plain-text fallback path below. This happens
    when Gemini's response fails the full JSON parse (so `json.loads` never
    runs to decode them) but the text itself still contains raw JSON string
    escapes — otherwise the user sees literal "\\u20b9" instead of "₹"."""
    if not text or "\\u" not in text:
        return text
    try:
        return re.sub(
            r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text
        )
    except Exception:
        return text


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


# ── Origin/destination geocoding for the budget-estimate flight distance ────
# The frontend's structured-wizard flow (ConversationalWizard.tsx) geocodes
# places via /geocode as the user types, but the live LLM-driven wizard
# (LLMWizard.tsx) doesn't — it just extracts city names as plain text into
# config_patch, so lat/lon here are always 0 unless we resolve them
# ourselves. Needed so core.budget_estimator can use the real-distance
# flight band instead of its flat per-destination-tier fallback number.

def _has_group(config: dict[str, Any]) -> bool:
    group = config.get("group") or {}
    return any(group.get(k) for k in ("adults", "kids", "seniors", "infants"))


async def _ensure_place_coords(place: dict[str, Any] | None) -> dict[str, Any] | None:
    """Best-effort: geocode a {"city": ...} dict that's missing lat/lon.
    Returns a small {"lat": ..., "lon": ...} patch, or None if there's
    nothing to resolve or geocoding fails. Never raises — a bad/rate-limited
    Nominatim response should never block the chat turn."""
    if not place:
        return None
    city = place.get("city")
    if not city or (place.get("lat") and place.get("lon")):
        return None
    try:
        result = await geocode_city(city)
        return {"lat": result.lat, "lon": result.lon}
    except Exception:
        logger.warning("Geocoding failed for %r — continuing without coordinates.", city, exc_info=True)
        return None


async def _resolve_origin_destination_coords(config: dict[str, Any]) -> dict[str, Any]:
    """Geocodes origin/destination for the budget-estimate flight-distance
    heuristic, but only once all three of group/destination/origin city are
    already known — otherwise the estimate can't use a number yet anyway
    (see core.budget_estimator's origin gate), so there's no reason to spend
    a Nominatim call on every earlier turn (purpose, pace, themes, ...)."""
    dest_city = (config.get("destination") or {}).get("city")
    origin_city = (config.get("origin") or {}).get("city")
    if not (_has_group(config) and dest_city and origin_city):
        return {}

    origin_coords, dest_coords = await asyncio.gather(
        _ensure_place_coords(config.get("origin")),
        _ensure_place_coords(config.get("destination")),
    )
    patch: dict[str, Any] = {}
    if origin_coords:
        patch["origin"] = origin_coords
    if dest_coords:
        patch["destination"] = dest_coords
    return patch


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

    # Last user message text, used only to detect an explicit economical/
    # premium preference for the budget-recommendation hint below.
    last_user_text = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), None
    )
    try:
        geocode_patch = await _resolve_origin_destination_coords(request.partial_config)
    except Exception:
        geocode_patch = {}

    config_for_hint = request.partial_config
    if geocode_patch:
        config_for_hint = copy.deepcopy(request.partial_config)
        for key, coords in geocode_patch.items():
            config_for_hint[key] = {**config_for_hint.get(key, {}), **coords}

    try:
        budget_hint = await budget_estimate_prompt_hint(config_for_hint, last_user_text)
    except Exception:
        budget_hint = ""
    try:
        currency_hint = currency_conversion_prompt_hint(last_user_text)
    except Exception:
        currency_hint = ""

    try:
        visa_hint = await _visa_hint_for(request.partial_config, last_user_text)
    except Exception:
        # Same contract as the budget/currency hints above: a hint that can't be
        # computed must not cost the user their turn.
        visa_hint = ""

    try:
        router_hint = _router_hint_for(last_user_text)
    except Exception:
        router_hint = ""

    system_prompt = WIZARD_SYSTEM_PROMPT.format(
        preloaded_destination=request.preloaded_destination or "None",
        collected_state=_summarise_state(request.partial_config),
        budget_estimate_hint=budget_hint or "(not applicable this turn)",
        currency_conversion_hint=currency_hint or "(not applicable this turn — user has not stated a foreign-currency amount)",
        visa_hint=visa_hint or "(none on file)",
        router_hint=router_hint or "(not applicable this turn)",
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

    import logging
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
        # Defensive: decode any literal `\uXXXX` escapes that survived a
        # double-escaped JSON string value (e.g. "\u20b9" left un-decoded
        # because the LLM emitted a doubly-escaped backslash) — no-op on
        # already-correct text.
        reply_text = _decode_stray_unicode_escapes(reply_text)
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
        # Canonicalise the closed-set fields (pace / scope / crowd_preference /
        # destination_mode) here rather than only at TripConfig validation.
        # This dict is both merged into the running config *and* returned to the
        # frontend store, and the rest of this module branches on exact values
        # (`mode == "fixed"`, `!= "exploring"`), so a stray "Moderate" or
        # "undecided" would otherwise steer the conversation for every remaining
        # turn before the generate call ever sees it.
        patch = normalise_choice_fields(patch)
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v

        # Persist any origin/destination coordinates we resolved above so the
        # frontend stores them and future turns don't need to re-geocode.
        for k, coords in geocode_patch.items():
            merged[k] = {**merged.get(k, {}), **coords}
            patch[k] = {**patch.get(k, {}), **coords} if isinstance(patch.get(k), dict) else coords

        # Safety net: the LLM occasionally acknowledges a purpose-chip tap (or
        # a purpose stated in plain prose, e.g. "a family trip to Bali") in
        # its reply text and moves on to the next question, without actually
        # emitting `purpose` in config_patch — leaving CURRENT_STATE never
        # recording it. Since _is_stale_chips (below) only replaces stale
        # chips when the field looks filled, this silently reproduces the
        # purpose chips under a reply that already moved past purpose (e.g.
        # asking about budget, or a budget-adjustment follow-up), and keeps
        # doing so on every subsequent turn until something backfills it.
        # Deterministically backfill from the raw chip tap, then from a
        # plain-English purpose keyword in the message, when possible.
        if not merged.get("purpose"):
            inferred_purpose = _infer_purpose_from_chip_tap(last_user_text) or _infer_purpose_from_free_text(last_user_text)
            if inferred_purpose:
                merged["purpose"] = inferred_purpose
                patch["purpose"] = inferred_purpose

        # Same backfill, same reason, for pace (chip tap, then plain prose).
        if not merged.get("pace"):
            inferred_pace = _infer_pace_from_chip_tap(last_user_text) or _infer_pace_from_free_text(last_user_text)
            if inferred_pace:
                merged["pace"] = inferred_pace
                patch["pace"] = inferred_pace

        # Same backfill, same reason, for budget — only from an explicit
        # rupee marker (₹ / rupees / rs / inr / lakh / crore), never a bare
        # number, to avoid misreading an unrelated digit (day count,
        # headcount, date) as a budget figure.
        if not (merged.get("budget") or {}).get("amount"):
            inferred_amount = _infer_budget_amount_from_free_text(last_user_text)
            if inferred_amount:
                merged["budget"] = {**(merged.get("budget") or {}), "amount": inferred_amount, "currency": "INR"}
                patch["budget"] = {**(patch.get("budget") or {}), "amount": inferred_amount, "currency": "INR"}

        # Same backfill, same reason, for group composition — only from an
        # explicit "adults" marker (see _infer_group_from_free_text).
        if not (merged.get("group") or {}).get("adults"):
            inferred_group = _infer_group_from_free_text(last_user_text)
            if inferred_group:
                merged["group"] = {**(merged.get("group") or {}), **inferred_group}
                patch["group"] = {**(patch.get("group") or {}), **inferred_group}

        # Same backfill, same reason, for dates — only from an explicit
        # day-range-within-one-month sentence (see _infer_dates_from_free_text
        # for exactly what's handled and why the scope is narrow).
        existing_dates = merged.get("dates") or {}
        if not (existing_dates.get("start") and existing_dates.get("end")):
            inferred_dates = _infer_dates_from_free_text(last_user_text)
            if inferred_dates:
                merged["dates"] = {**existing_dates, **inferred_dates}
                patch["dates"] = {**(patch.get("dates") or {}), **inferred_dates}

        # Same backfill, same reason, for destination — only from the
        # opening message (see _infer_destination_from_free_text for why
        # this is restricted to the first turn), and only when the model
        # hasn't already put the trip in "exploring"/"country" mode itself.
        if (
            len(request.messages) <= 1
            and not (merged.get("destination") or {}).get("city")
            and merged.get("destination_mode", "fixed") == "fixed"
        ):
            inferred_destination = await _infer_destination_from_free_text(last_user_text)
            if inferred_destination:
                merged["destination"] = {**(merged.get("destination") or {}), **inferred_destination}
                patch["destination"] = {**(patch.get("destination") or {}), **inferred_destination}
                merged["destination_mode"] = "fixed"
                patch["destination_mode"] = "fixed"

        # Hard, non-LLM sanity floor (⭐ NEW): fires the instant a budget
        # figure is recorded, using whatever destination/dates/group is
        # already known (a real, itemised floor — not a flat generic number)
        # — see _absolute_budget_floor_warning. An amount that fails it is
        # deliberately NOT stored as "filled": stripping it out of both
        # `merged` and `patch` keeps the budget field genuinely missing so
        # the wizard asks again instead of silently treating an impossible
        # number as valid input.
        budget_floor_warning = await _absolute_budget_floor_warning(merged)
        if budget_floor_warning:
            reply_text = budget_floor_warning
            chips_list = []
            merged["budget"] = {**(merged.get("budget") or {}), "amount": 0}
            patch.pop("budget", None)

        # Server-side override: only allow ready=true if all required fields present
        ready = data.get("ready_to_generate", False) and _has_all_required(merged)

        # One-shot trigger guard (⭐ NEW, see Section 7 Stage 3): all 6 fields
        # being present is necessary but not sufficient — ready_to_generate
        # must only fire on the SPECIFIC turn budget transitions from
        # missing to present, or on an explicit user regenerate/update
        # request (edit mode, or asking again later). Without this, every
        # subsequent turn after budget was already set (an unrelated
        # follow-up question, a checkpoint-style aside, etc.) would re-fire
        # the automatic feasibility check / auto-generation.
        if ready:
            budget_was_already_present = (request.partial_config.get("budget") or {}).get("amount", 0) > 0
            budget_just_recorded_this_turn = not budget_was_already_present and merged.get("budget", {}).get("amount", 0) > 0
            explicit_regenerate_request = bool(last_user_text and _EXPLICIT_REGENERATE_RE.search(last_user_text))
            if not (budget_just_recorded_this_turn or explicit_regenerate_request):
                ready = False

        # Anti-hallucination safety net: if the model's own reply text falsely
        # implies generation is happening/done while `ready` is False this
        # turn, the user is left stuck with a confident-sounding lie and no
        # real next step (no loader, no CTA, nothing generated). Override
        # with an honest prompt for whatever's actually still missing.
        if not ready and _HALLUCINATED_GENERATION_RE.search(reply_text):
            reply_text, chips_list = _next_missing_field_prompt(merged)

        # Safety net: the very first turn always asks about trip purpose (system
        # prompt Section 4, Field 1 mandates chips here), but with almost no
        # conversation context yet, the LLM occasionally omits them. Since this
        # is the single highest-traffic touchpoint (every user's first message),
        # deterministically backfill the standard purpose chips rather than
        # leaving the opening question chip-less.
        if not chips_list and not merged.get("purpose") and len(request.messages) <= 1:
            chips_list = ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"]

        # Safety net: the model sometimes echoes a PREVIOUS turn's chip set
        # instead of the one for the field it's actually asking about this
        # turn — observed in the wild as the purpose chips (Leisure/Adventure/
        # ...) reappearing under a reply that had already moved on to asking
        # about destination. Detect chips that belong to a field CURRENT_STATE
        # says is already filled, and replace them with the chips for whatever
        # is genuinely still missing.
        if chips_list and _is_stale_chips(chips_list, merged):
            _, fresh_chips = _next_missing_field_prompt(merged)
            chips_list = fresh_chips

        # Bug fix: the reply text is asking for the departure city (a
        # free-form answer, no chips of its own) — drop any chips the LLM
        # attached, most commonly stale Pace chips, since pace isn't
        # "filled" yet at this point in the conversation and so isn't
        # caught by the stale-chips check above.
        if chips_list and _is_departure_city_question(reply_text):
            chips_list = []

        # Bug fix: don't re-offer Stage 2 "anything else?" checkpoint chips
        # for optional fields the user already answered (e.g. "Add
        # departure city" once origin.city is known) — this flow never
        # revisits already-filled optional fields outside a feasibility-
        # adjustment/itinerary-edit exchange, which live in separate chains.
        if chips_list:
            chips_list = _filter_answered_checkpoint_chips(chips_list, merged)

        # Bug fix: the user just tapped a destination-MODE chip ("Suggest
        # me!" / "I have a destination in mind") — the very next question
        # ("Where are you thinking of going?" / "Could you tell me the
        # destination?") expects a free-form place name, not another tap of
        # the mode they already picked. Drop the mode chips if the LLM
        # echoed them verbatim under this follow-up.
        if chips_list and _is_destination_mode_chip_tap(last_user_text) and frozenset(chips_list) == _FIELD_CHIP_SETS["destination"]:
            chips_list = []

        # Bug fix: the user just tapped a group-TYPE chip (Solo/Couple/
        # Family/Friends) — the very next question asks for actual traveler
        # counts (adults/children/seniors), which expects free-form numbers,
        # not another tap of the type they already picked. Drop the group
        # chips if the LLM echoed them verbatim under this follow-up.
        if chips_list and _is_group_type_chip_tap(last_user_text) and frozenset(chips_list) == _FIELD_CHIP_SETS["group"]:
            chips_list = []

        # Safety net (general, any turn): the same "LLM asks the right
        # question but drops the chips" failure mode observed above for the
        # opening purpose question also happens later in the conversation —
        # e.g. asking about pace/group in plain text with no chips (seen in
        # the wild: "would you prefer a relaxed pace, moderate, or packed?"
        # with an empty chips array). Fields with a fixed enum always have a
        # canonical chip set (see _next_missing_field_prompt); if chips are
        # still empty and the next actually-missing field is one of those,
        # backfill just the chips — the LLM's own wording is left untouched.
        # Exception: don't backfill the destination-MODE chips right after
        # the user already tapped one of them (see above) — that would
        # reintroduce the same bug via this fallback path instead. Same
        # exception for group-TYPE chips: `_next_missing_field_prompt` still
        # considers `group` "missing" right after a type-chip tap (since
        # `adults` isn't set until the follow-up counts question is
        # answered), so it would otherwise re-suggest the group-type
        # question/chips even though the reply text has already moved on to
        # asking for counts.
        if not chips_list and not ready and not _is_departure_city_question(reply_text):
            _, fallback_chips = _next_missing_field_prompt(merged)
            is_destination_mode_fallback = frozenset(fallback_chips) == _FIELD_CHIP_SETS["destination"]
            is_group_fallback = frozenset(fallback_chips) == _FIELD_CHIP_SETS["group"]
            if (
                fallback_chips
                and fallback_chips != ["Just generate it! 🚀"]
                and not (is_destination_mode_fallback and _is_destination_mode_chip_tap(last_user_text))
                and not (is_group_fallback and _is_group_type_chip_tap(last_user_text))
            ):
                chips_list = fallback_chips

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

        # Safety net: same purpose-chip-tap inference as the JSON-success
        # path above. This except branch is, in practice, the one actually
        # hit whenever Gemini's JSON is malformed (e.g. duplicated/truncated
        # output) — request.partial_config never gets a `purpose` patch
        # applied client-side in that case either, so every fallback below
        # that reads request.partial_config would otherwise re-offer the
        # purpose chips forever, even after the user already tapped one.
        fallback_config = dict(request.partial_config)
        fallback_patch: dict[str, Any] = {}
        for k, coords in geocode_patch.items():
            fallback_config[k] = {**fallback_config.get(k, {}), **coords}
            fallback_patch[k] = coords
        if not fallback_config.get("purpose"):
            inferred_purpose = _infer_purpose_from_chip_tap(last_user_text) or _infer_purpose_from_free_text(last_user_text)
            if inferred_purpose:
                fallback_config["purpose"] = inferred_purpose
                fallback_patch["purpose"] = inferred_purpose

        # Same backfill, same reason, for pace and budget (see JSON-success
        # path above for the full rationale).
        if not fallback_config.get("pace"):
            inferred_pace = _infer_pace_from_chip_tap(last_user_text) or _infer_pace_from_free_text(last_user_text)
            if inferred_pace:
                fallback_config["pace"] = inferred_pace
                fallback_patch["pace"] = inferred_pace
        if not (fallback_config.get("budget") or {}).get("amount"):
            inferred_amount = _infer_budget_amount_from_free_text(last_user_text)
            if inferred_amount:
                fallback_config["budget"] = {**(fallback_config.get("budget") or {}), "amount": inferred_amount, "currency": "INR"}
                fallback_patch["budget"] = {**(fallback_patch.get("budget") or {}), "amount": inferred_amount, "currency": "INR"}

        # Same backfill, same reason, for group composition (see
        # _infer_group_from_free_text) — this is the fix for the observed
        # prod bug: without it, `fallback_config` here is just
        # `request.partial_config` (pre-patch), so a malformed-JSON turn that
        # answers the group-composition question left `adults` at 0 and
        # `_is_stale_chips` below never recognised the stale group chips.
        if not (fallback_config.get("group") or {}).get("adults"):
            inferred_group = _infer_group_from_free_text(last_user_text)
            if inferred_group:
                fallback_config["group"] = {**(fallback_config.get("group") or {}), **inferred_group}
                fallback_patch["group"] = {**(fallback_patch.get("group") or {}), **inferred_group}

        # Same backfill, same reason, for dates (see _infer_dates_from_free_text).
        existing_fallback_dates = fallback_config.get("dates") or {}
        if not (existing_fallback_dates.get("start") and existing_fallback_dates.get("end")):
            inferred_dates = _infer_dates_from_free_text(last_user_text)
            if inferred_dates:
                fallback_config["dates"] = {**existing_fallback_dates, **inferred_dates}
                fallback_patch["dates"] = {**(fallback_patch.get("dates") or {}), **inferred_dates}

        # Same backfill, same reason, for destination (see JSON-success path
        # above and _infer_destination_from_free_text for why this is
        # restricted to the opening turn).
        if (
            len(request.messages) <= 1
            and not (fallback_config.get("destination") or {}).get("city")
            and fallback_config.get("destination_mode", "fixed") == "fixed"
        ):
            inferred_destination = await _infer_destination_from_free_text(last_user_text)
            if inferred_destination:
                fallback_config["destination"] = {**(fallback_config.get("destination") or {}), **inferred_destination}
                fallback_patch["destination"] = {**(fallback_patch.get("destination") or {}), **inferred_destination}
                fallback_config["destination_mode"] = "fixed"
                fallback_patch["destination_mode"] = "fixed"

        # Hard, non-LLM sanity floor (⭐ NEW, same as JSON-success path above)
        # — real, destination-aware floor using whatever's known so far. An
        # amount that fails it is stripped back out so budget stays "missing".
        fallback_budget_floor_warning = await _absolute_budget_floor_warning(fallback_config)
        if fallback_budget_floor_warning:
            clean_raw = fallback_budget_floor_warning
            extracted_chips = []
            fallback_config["budget"] = {**(fallback_config.get("budget") or {}), "amount": 0}
            fallback_patch.pop("budget", None)

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

        # Decode any literal JSON `\uXXXX` escapes (e.g. `\u20b9` -> ₹) left
        # over because this text never went through json.loads on this path.
        clean_raw = _decode_stray_unicode_escapes(clean_raw)

        # Same first-turn purpose-chip safety net as the JSON-success path
        # above: a plain-text (non-JSON) greeting response on the very first
        # turn should still offer the standard purpose chips rather than
        # leaving the user with no way to respond except free text.
        if not extracted_chips and not fallback_config.get("purpose") and len(request.messages) <= 1:
            extracted_chips = ["Leisure 🌴", "Adventure 🏔️", "Honeymoon 💑", "Family Vacation 👨‍👩‍👧", "Friends Trip 🎉", "Solo 🧳"]

        # General any-turn chip backfill — same rationale as the JSON-success
        # path above (this fallback fires whenever the LLM's raw response
        # wasn't valid JSON at all, so it never had a `chips` field to begin
        # with; the fixed-enum fields still deserve their canonical chips).
        if not extracted_chips and not _is_departure_city_question(clean_raw):
            _, fallback_chips = _next_missing_field_prompt(fallback_config)
            is_destination_mode_fallback = frozenset(fallback_chips) == _FIELD_CHIP_SETS["destination"]
            is_group_fallback = frozenset(fallback_chips) == _FIELD_CHIP_SETS["group"]
            if (
                fallback_chips
                and fallback_chips != ["Just generate it! 🚀"]
                and not (is_destination_mode_fallback and _is_destination_mode_chip_tap(last_user_text))
                and not (is_group_fallback and _is_group_type_chip_tap(last_user_text))
            ):
                extracted_chips = fallback_chips

        # Anti-hallucination safety net (see the JSON-success path above for
        # full rationale) — this plain-text fallback path ALWAYS returns
        # ready_to_generate=False, so a falsely-confident "it's ready!" here
        # would be even more misleading since there's no backing config_patch
        # either.
        if clean_raw and _HALLUCINATED_GENERATION_RE.search(clean_raw):
            clean_raw, extracted_chips = _next_missing_field_prompt(fallback_config)

        # Safety net: strip a stale echoed chip set (e.g. purpose chips under
        # a reply that's already moved on) the same way the JSON-success
        # path does — the plain-text extraction above can still surface an
        # old chip set embedded in the leaked text.
        if extracted_chips and _is_stale_chips(extracted_chips, fallback_config):
            _, extracted_chips = _next_missing_field_prompt(fallback_config)

        # Bug fix (see JSON-success path above): the reply is asking for the
        # departure city (free-form answer) — drop any stray chips (most
        # commonly stale Pace chips, since pace isn't filled yet here).
        if extracted_chips and _is_departure_city_question(clean_raw):
            extracted_chips = []

        # Bug fix (see JSON-success path above): don't re-offer Stage 2
        # checkpoint chips for optional fields already answered.
        if extracted_chips:
            extracted_chips = _filter_answered_checkpoint_chips(extracted_chips, fallback_config)

        # Bug fix (see JSON-success path above): don't echo the destination
        # MODE chips right back after the user just tapped one of them.
        if extracted_chips and _is_destination_mode_chip_tap(last_user_text) and frozenset(extracted_chips) == _FIELD_CHIP_SETS["destination"]:
            extracted_chips = []

        # Bug fix (see JSON-success path above): don't echo the group-TYPE
        # chips right back after the user just tapped one of them — the
        # follow-up question expects traveler counts, not another tap.
        if extracted_chips and _is_group_type_chip_tap(last_user_text) and frozenset(extracted_chips) == _FIELD_CHIP_SETS["group"]:
            extracted_chips = []

        # Bug fix: when Gemini's response was unusable (empty/unparseable),
        # `clean_raw` ends up empty here and we used to paper over it with a
        # static "I'm on it! Just a moment…" placeholder. That text falsely
        # implies more processing is coming, but this is a synchronous
        # request/response call — nothing else arrives, so the chat visibly
        # stalls until the user sends another message to trigger a fresh
        # turn. Ask the actual next missing question instead, so every turn
        # ends with a real, answerable prompt.
        if not clean_raw:
            clean_raw, honest_chips = _next_missing_field_prompt(fallback_config)
            if not extracted_chips:
                extracted_chips = honest_chips

        return WizardChatResponse(
            reply=clean_raw,
            chips=extracted_chips,
            config_patch=fallback_patch,
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
    if not (config.get("group", {}).get("adults", 0) >= 1):
        return WizardChatResponse(reply="Who will be joining you — travelling solo, as a couple, or with family?", chips=["Solo 🧳", "Couple ❤️", "Family 👨‍👩‍👧", "Friends 🎉"], config_patch={}, ready_to_generate=False)
    if not config.get("pace"):
        return WizardChatResponse(reply="What pace works for you?", chips=["Relaxed 🧘", "Moderate 🚶", "Packed 🏃"], config_patch={}, ready_to_generate=False)
    if not (config.get("budget", {}).get("amount", 0) > 0):
        return WizardChatResponse(
            reply=f"What's your approximate budget in ₹ (INR)? (Or tell me in {', '.join(TOP_10_CURRENCIES)} — I'll convert.)",
            chips=[], config_patch={}, ready_to_generate=False,
        )

    return WizardChatResponse(
        reply="I'm having a little trouble right now — please try again in a moment.",
        chips=[], config_patch={}, ready_to_generate=False,
    )
