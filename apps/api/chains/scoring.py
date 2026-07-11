"""
Alignment score: fixed weights in Phase 1 per PRD Section 6.2.
Score is internal only — never displayed to users.
"""
from __future__ import annotations
from models.itinerary import ItineraryItem
from models.trip import TripConfig
from core.budget_tiers import resolve_budget_tier

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

# Tag vocabularies used by the budget-fit heuristic (no per-item cost data
# exists in ItineraryItem, so this is a tag-based proxy, not a real cost
# computation — see docs design memo Part 2.2/2.5).
_BUDGET_LEANING_TAGS = {"budget", "free", "street_food", "public", "hostel"}
_PREMIUM_LEANING_TAGS = {"premium", "luxury", "fine_dining", "private", "exclusive"}

# Which budget category (matches BUDGET_CATEGORIES in core/budget_tiers.py)
# a given item most plausibly belongs to, inferred from its tags.
_CATEGORY_TAGS: dict[str, set[str]] = {
    "food": {"food", "restaurant", "dining", "street_food", "fine_dining", "cafe"},
    "activities": {"activity", "adventure", "museum", "tour", "attraction", "sports"},
    "shopping": {"shopping", "market", "souvenir"},
    "local_transport": {"transport", "transit"},
}


def calculate_alignment_score(item: ItineraryItem, trip_config: TripConfig) -> float:
    persona_match = _persona_match(item.tags, trip_config.personas)
    budget_score = _budget_fit(item, trip_config)

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


def _item_category(tags: set[str]) -> str | None:
    for category, cat_tags in _CATEGORY_TAGS.items():
        if tags & cat_tags:
            return category
    return None


def _budget_fit(item: ItineraryItem, trip_config: TripConfig) -> float:
    """Tag-based proxy for "does this item fit the trip's resolved budget
    tier and any splurge/save preferences". Not a real cost computation —
    ItineraryItem carries no per-item price — but it replaces the previous
    hardcoded `budget_score = 1.0` (which had zero effect on anything) with
    a signal that actually reflects the persona/purpose budget tier and the
    user's explicit splurge/save category choices.
    """
    tags = {t.lower() for t in item.tags}
    tier = resolve_budget_tier(trip_config)["tier_label"]
    score = 1.0

    is_budget_leaning = bool(tags & _BUDGET_LEANING_TAGS)
    is_premium_leaning = bool(tags & _PREMIUM_LEANING_TAGS)

    if "budget" in tier:
        if is_budget_leaning:
            score += 0.15
        elif is_premium_leaning:
            score -= 0.15
    elif "luxury" in tier or "premium" in tier:
        if is_premium_leaning:
            score += 0.15
        elif is_budget_leaning:
            score -= 0.05  # a cheap stop in a luxury trip isn't necessarily bad

    category = _item_category(tags)
    splurge = set(getattr(trip_config, "splurge_categories", None) or [])
    save = set(getattr(trip_config, "save_categories", None) or [])
    if category:
        if category in splurge and is_premium_leaning:
            score += 0.10
        if category in save:
            if is_budget_leaning:
                score += 0.10
            elif is_premium_leaning:
                score -= 0.15

    return max(0.0, min(1.0, score))


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
