"""
Kid safety filtering and persona module injection for generated itinerary days.
PRD Section 6.2 / Clarification #3.
"""
from models.itinerary import ItineraryDay, ItineraryItem, ItineraryItemLocation
from models.trip import TripConfig

# OSM-derived tags / title keywords that indicate kid-excluded venues
KID_EXCLUDED_TAGS = {
    "bar", "nightclub", "nightlife", "adult", "extreme_sports",
    "bungee", "skydiving", "casino", "hookah", "strip_club",
}

KID_EXCLUDED_TITLE_KEYWORDS = {
    "bar", "pub", "nightclub", "club", "casino", "bungee", "skydive",
    "extreme", "strip", "hookah", "brewery tap", "cocktail lounge",
}


def apply_kid_safety_filter(
    days: list[ItineraryDay], trip_config: TripConfig
) -> list[ItineraryDay]:
    if not trip_config.group.has_kids and not trip_config.group.has_infants:
        return days

    filtered_days = []
    for day in days:
        safe_items = [item for item in day.items if _is_kid_safe(item)]
        day.items = safe_items
        filtered_days.append(day)
    return filtered_days


def _is_kid_safe(item: ItineraryItem) -> bool:
    tag_set = {t.lower() for t in item.tags}
    if tag_set & KID_EXCLUDED_TAGS:
        return False
    title_lower = item.title.lower()
    if any(kw in title_lower for kw in KID_EXCLUDED_TITLE_KEYWORDS):
        return False
    return True


def inject_persona_modules(
    days: list[ItineraryDay], trip_config: TripConfig
) -> list[ItineraryDay]:
    """
    Post-process: if the LLM missed persona-specific blocks, inject placeholders.
    This is a safety net — the system prompt should handle most cases.
    """
    personas = set(trip_config.personas)

    for day in days:
        existing_tags = {tag for item in day.items for tag in item.tags}

        if "digital_nomad" in personas and "work_block" not in existing_tags:
            day.items.append(_make_work_block(day.date))

        if "sports_fitness" in personas and "training_window" not in existing_tags:
            day.items.append(_make_training_block(day.date))

    return days


def _make_work_block(date: str) -> ItineraryItem:
    import uuid
    return ItineraryItem(
        id=str(uuid.uuid4()),
        time_start="09:00",
        time_end="11:00",
        title="Work Block — Local Coworking / Café",
        description="Dedicated 2-hour work window. Look for a wifi-equipped café or coworking space near your accommodation.",
        location=ItineraryItemLocation(lat=0.0, lon=0.0, address="TBD — search locally"),
        tags=["work_block", "wifi", "digital_nomad"],
    )


def _make_training_block(date: str) -> ItineraryItem:
    import uuid
    return ItineraryItem(
        id=str(uuid.uuid4()),
        time_start="07:00",
        time_end="08:00",
        title="Training Window — Gym / Trail",
        description="1-hour morning training window. Check hotel gym or nearby OSM-tagged running trail.",
        location=ItineraryItemLocation(lat=0.0, lon=0.0, address="TBD — search locally"),
        tags=["training_window", "outdoor", "sports_fitness"],
    )
