"""Shared chip classification for every conversational surface.

A "chip" is a tappable quick-reply option a chain returns alongside its text.
Whether a group is *multi*-select — pick several, then continue — or
single-select — one tap submits — is decided **here, server-side and
deterministically**, and shipped to the client as a boolean.

⚠️ **This module exists so that a second chat surface cannot drift from the
first.** `wizard_chat_chain` owned this logic privately; when `chat_refine_chain`
grew chips it would have needed the same rules, and this codebase has already
paid for that pattern once — v10.46's `normalise_choice_fields` had to be
applied at *two* independent patch-merge points, and fixing only one would have
fixed nothing. Any new chain that emits chips imports from here rather than
copying.

⚠️ **Chip labels must stay in English even when the conversation is not.**
Classification is keyword-based, so a translated chip fails the theme test and
silently downgrades a multi-select group to single-select — a wrong UI, not a
visible error. `WIZARD_SYSTEM_PROMPT` §3a already pins this for the wizard; the
same constraint binds any chain added later.
"""
from __future__ import annotations

from core.keyword_match import has_keyword

# Keywords that identify a multi-value field's chip options (themes today;
# extend this list if other multi-select fields grow chip UIs later).
MULTI_SELECT_CHIP_KEYWORDS = [
    "culture", "nature", "food", "adventure", "shopping", "photography",
    "nightlife", "sports", "wellness", "religious", "vegetarian",
]

# Generic catch-all chips (e.g. "No preference") that can appear alongside a
# theme-chip group without being a theme themselves. They must NOT break the
# "every chip looks like a theme" check below, or the whole group silently
# falls back to single-select — which was the actual bug: the themes prompt
# always appends one of these, so multi-select was never detected.
GENERIC_CHIP_KEYWORDS = ["no preference", "none", "skip", "any", "no thanks", "not sure"]


def is_multi_select_chips(chips: list[str]) -> bool:
    """True if every non-generic chip looks like a travel-theme option,
    meaning the user should be able to select several before continuing."""
    if len(chips) < 2:
        return False
    theme_chips = [
        chip for chip in chips
        # Word-boundary matching, via has_keyword: "any" is inside
        # "Germany"/"Tuscany"/"Albany", which were being classed as generic
        # "no preference" chips and dropped.
        if not has_keyword(chip, GENERIC_CHIP_KEYWORDS)
    ]
    if not theme_chips:
        return False
    return all(
        has_keyword(chip, MULTI_SELECT_CHIP_KEYWORDS)
        for chip in theme_chips
    )
