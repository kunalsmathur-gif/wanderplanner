"""Shared chip classification for every conversational surface.

A "chip" is a tappable quick-reply option a chain returns alongside its text.
Whether a group is *multi*-select — pick several, then continue — or
single-select — one tap submits — is decided **here, server-side and
deterministically**, and shipped to the client as a boolean.

⚠️ **Only `wizard_chat_chain` emits chips today, and that is deliberate.**
This module was extracted (v10.61) while preparing to give the orb chat the
same chip UI; that plan was then dropped, and the reasoning is worth keeping
because it will come up again. A chip is an *answer to a pending question* —
the wizard always has one, since it is slot-filling one field at a time, so
chips there are effectively form controls. The orb chat has no pending
question: the user drives, and most turns are open ("is day 3 too packed?").
Attaching chips to open turns narrows what users believe they may ask, and
forces the model to judge per-turn when chips help — a judgement it will get
wrong in the user's face. Multi-select is worse: "pick several, then continue"
needs a *next question* to continue to, which free chat does not have.
`ChatPanel` handles its one genuinely closed-set moment — the regenerate
confirmation — with a purpose-built pair of buttons instead, which is the
right shape.

So this module is shared-*ready* rather than currently shared. It stays here
regardless, because the alternative to one tested implementation is two
untested copies, and this codebase has already paid for that pattern once:
v10.46's `normalise_choice_fields` had to be applied at *two* independent
patch-merge points, and fixing only one would have fixed nothing. Any chain
that does grow chips imports from here rather than copying.

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
