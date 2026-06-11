"""
Alignment score: fixed weights in Phase 1 per PRD Section 6.2.
Score is internal only — never displayed to users.
"""
from __future__ import annotations
from models.itinerary import ItineraryItem
from models.trip import TripConfig

# Fixed weights — Phase 1 (dynamic per-persona weights deferred to Phase 2)
W_PERSONA = 0.5
W_BUDGET = 0.3
W_ACCESS = 0.2

# Fixed social penalty per negative keyword
SOCIAL_PENALTY = 0.05

NEGATIVE_KEYWORDS = {"avoid", "dangerous", "scam", "unsafe", "closed", "overrated"}

# Rough persona-to-tag affinity mapping for persona match heuristic
PERSONA_TAG_AFFINITY: dict[str, set[str]] = {
    "digital_nomad": {"work_block", "wifi", "coworking", "cafe"},
    "aesthetic_explorer": {"instaworthy", "scenic", "photography", "art"},
    "pet_parent": {"pet_friendly", "dog_friendly", "outdoor", "park"},
    "retired_traveler": {"cultural", "museum", "relaxed", "accessible"},
    "sports_fitness": {"training_window", "outdoor", "trail", "sports"},
    "group_coordinator": {"family", "kid_friendly", "group", "activity"},
}


def calculate_alignment_score(item: ItineraryItem, trip_config: TripConfig) -> float:
    persona_match = _persona_match(item.tags, trip_config.personas)

    per_item_budget = (
        trip_config.budget.amount / max(
            sum(1 for _ in range(5)) * len(trip_config.dates.get("start", "1") or "1"),
            1,
        )
        if trip_config.budget.amount > 0
        else float("inf")
    )
    # Budget score: full marks if no cost data available (item has no cost field)
    budget_score = 1.0

    access_score = (
        1.0
        if not trip_config.accommodation.wheelchair_accessible
        else (1.0 if "accessible" in item.tags else 0.6)
    )

    social_penalty = sum(
        SOCIAL_PENALTY for kw in NEGATIVE_KEYWORDS if kw in item.description.lower()
    )

    raw = (W_PERSONA * persona_match) + (W_BUDGET * budget_score) + (W_ACCESS * access_score)
    raw = max(0.0, raw - social_penalty)
    return round(raw * 100, 2)


def _persona_match(item_tags: list[str], personas: list[str]) -> float:
    if not personas:
        return 0.85  # default neutral score
    tag_set = set(item_tags)
    matched = 0
    for persona in personas:
        affinity = PERSONA_TAG_AFFINITY.get(persona, set())
        if tag_set & affinity:
            matched += 1
    return min(1.0, 0.5 + (matched / len(personas)) * 0.5)
