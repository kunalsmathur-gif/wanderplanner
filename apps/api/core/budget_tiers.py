"""
Persona/purpose -> budget-tier resolution.

Phase 1 of the budget-curation roadmap (docs/rag-strategy.md-adjacent design
memo, Part 2.2): today the cost-estimation prompt has no persona-aware
guidance at all — every trip gets the same generic "be conservative, use
average market rates" instruction regardless of whether the traveller is a
`budget_backpacker` or a `luxury_traveller`. This module is a small,
hand-authored lookup table (not ML) that maps `personas` + `purpose` to a
concrete accommodation/dining tier, and renders it as a prompt-ready hint
string consumed by both `chains/itinerary_chain.py` (day-plan generation)
and `chains/feasibility_chain.py` (cost feasibility check).

No external calls, no cost — pure rule-based mapping.
"""
from __future__ import annotations
from models.trip import TripConfig

# Ordered by priority: if a user has multiple personas that imply a tier,
# the first match in this list wins (luxury/budget signals are the
# strongest, explicit budget statements; senior/digital-nomad/sports/pet
# personas don't imply a spending tier on their own).
PERSONA_TIER_PRIORITY: list[str] = ["luxury_traveller", "budget_backpacker", "senior_traveller"]

PERSONA_TIERS: dict[str, dict[str, str]] = {
    "luxury_traveller": {
        "tier_label": "luxury",
        "accommodation_hint": "4-5 star hotels, boutique resorts, or premium villas",
        "dining_hint": "fine dining and highly-rated restaurants; avoid street food/budget chains",
        "notes": "Prioritize experience quality over cost savings. Private transport over public transit where reasonable.",
    },
    "budget_backpacker": {
        "tier_label": "budget",
        "accommodation_hint": "hostels, budget guesthouses, or dorm-style stays",
        "dining_hint": "street food, local eateries, self-catering where possible",
        "notes": "Prioritize cost savings. Public transport over taxis. Free/low-cost activities preferred.",
    },
    "senior_traveller": {
        "tier_label": "mid-range",
        "accommodation_hint": "comfortable 3-4 star hotels with easy accessibility",
        "dining_hint": "sit-down restaurants, avoid excessive walking-heavy street-food crawls",
        "notes": "Prioritize comfort and accessibility over cost savings; avoid overly packed schedules.",
    },
}

# Fallback mapping when no tier-signalling persona is present — derived from
# `purpose` instead. Every purpose maps to *something* so the prompt hint is
# never empty.
PURPOSE_TIERS: dict[str, dict[str, str]] = {
    "honeymoon": {
        "tier_label": "mid-range-to-premium",
        "accommodation_hint": "boutique hotels or romantic resorts, prefer a couple's room/suite",
        "dining_hint": "mostly local restaurants, but include one memorable/upscale meal",
        "notes": "Include exactly one 'splurge' experience in the trip (e.g. a rooftop dinner, a private sunset tour, a couple's spa) even if the rest of the trip is mid-range.",
    },
    "family_vacation": {
        "tier_label": "mid-range",
        "accommodation_hint": "family rooms or connecting rooms at 3-4 star hotels/resorts",
        "dining_hint": "family-friendly restaurants with varied menus",
        "notes": "Balance cost with convenience — avoid long transit gaps with young kids in tow.",
    },
    "business_leisure": {
        "tier_label": "premium",
        "accommodation_hint": "business-friendly 4-5 star hotels with reliable wifi",
        "dining_hint": "convenient, efficient dining near the accommodation/work areas",
        "notes": "Time efficiency matters as much as cost — minimize long transit for leisure add-ons.",
    },
    "solo_backpacking": {
        "tier_label": "budget",
        "accommodation_hint": "hostels or budget guesthouses",
        "dining_hint": "street food and local eateries",
        "notes": "Prioritize cost savings and flexibility over comfort.",
    },
    "group_holiday": {
        "tier_label": "mid-range",
        "accommodation_hint": "mid-range hotels with group/multi-bed room options",
        "dining_hint": "group-friendly restaurants that can accommodate larger tables",
        "notes": "Favor activities and venues that work well for a larger group.",
    },
    "adventure": {
        "tier_label": "mid-range",
        "accommodation_hint": "practical, well-located mid-range stays (proximity to trailheads/activities matters more than luxury)",
        "dining_hint": "hearty, convenient local food",
        "notes": "Budget skews toward activity/gear costs over accommodation luxury.",
    },
    "leisure": {
        "tier_label": "mid-range",
        "accommodation_hint": "standard 3-4 star hotels",
        "dining_hint": "a mix of local restaurants and casual dining",
        "notes": "Balanced default — no strong skew toward splurging or saving.",
    },
}

_DEFAULT_TIER = PURPOSE_TIERS["leisure"]

# Valid budget categories a user can flag to splurge/save on (Part 2.5 of
# the design memo). Kept in sync with `ExpenseBreakdown` line items.
BUDGET_CATEGORIES: list[str] = ["accommodation", "food", "activities", "shopping", "local_transport"]


def resolve_budget_tier(trip_config: TripConfig) -> dict[str, str]:
    """Resolve the effective budget tier for a trip: persona signal takes
    priority over purpose; purpose is always available as a fallback so this
    never returns an empty/unknown tier."""
    personas = set(trip_config.personas or [])
    for persona in PERSONA_TIER_PRIORITY:
        if persona in personas:
            return PERSONA_TIERS[persona]

    purpose = (trip_config.purpose or "").strip().lower()
    return PURPOSE_TIERS.get(purpose, _DEFAULT_TIER)


def budget_tier_prompt_hint(trip_config: TripConfig) -> str:
    """Render the resolved tier + any splurge/save category preferences as a
    prompt-ready guidance block for the itinerary/feasibility prompts."""
    tier = resolve_budget_tier(trip_config)
    lines = [
        f"BUDGET TIER GUIDANCE: {tier['tier_label']} tier.",
        f"- Accommodation: {tier['accommodation_hint']}",
        f"- Dining: {tier['dining_hint']}",
        f"- {tier['notes']}",
    ]

    splurge = getattr(trip_config, "splurge_categories", None) or []
    save = getattr(trip_config, "save_categories", None) or []
    if splurge:
        lines.append(
            f"- User wants to SPLURGE on: {', '.join(splurge)} — allocate more budget here than the tier default, "
            "even if it means trimming elsewhere."
        )
    if save:
        lines.append(
            f"- User wants to SAVE on: {', '.join(save)} — keep this category as low-cost as reasonably possible."
        )

    return "\n".join(lines)
