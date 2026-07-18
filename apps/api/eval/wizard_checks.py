"""Deterministic per-turn invariant checks for the wizard multi-turn eval
(eval/run_wizard_eval.py). Each check receives a single turn's full record
and returns (passed: bool, detail: str) -- never raises, so one bad check
never aborts the run.

These are state-machine correctness checks, not quality/preference judging
-- they encode invariants the wizard's own code already claims to guarantee
(see chains/wizard_chat_chain.py's `_is_stale_chips`, `_FIELD_CHIP_SETS`,
`_has_all_required`) and catch regressions where the LLM's live output (or
our own post-processing fallback) violates them. Reuses the production
module's own helpers/constants rather than re-encoding them, so a change to
the canonical chip sets or required-fields logic doesn't silently drift the
eval out of sync with the real behavior.
"""
from __future__ import annotations

from typing import Any, Callable

from chains.wizard_chat_chain import _FIELD_CHIP_SETS, _has_all_required, _is_stale_chips

TurnRecord = dict[str, Any]
CheckFn = Callable[[TurnRecord], tuple[bool, str]]

# Keyword lexicons per canonical fixed-chip field, used only to detect when
# a reply is CLEARLY talking about a different topic than the chips it
# offers (see check_chip_topic_alignment). Deliberately conservative/narrow
# -- false negatives (missing a real mismatch) are acceptable, false
# positives (flagging a legitimate reply) are not, since this runs against
# live, non-deterministic LLM output every time.
#
# A reply legitimately RECAPS the field it just filled before asking the
# next question (e.g. "Got it, a budget of 1 lakh -- perfect! And who will
# be joining?" with group chips) -- that recap alone must never trip this
# check. So a mismatch is only flagged when the reply contains an
# off-topic keyword for a DIFFERENT field AND contains none of the target
# field's own keywords (i.e. the reply never actually gets around to asking
# about the field the chips represent at all -- the real 2026-07-18 bug
# shape: a pure budget-breakdown reply with pace chips underneath, no
# mention of pace anywhere).
_TARGET_KEYWORDS: dict[str, list[str]] = {
    "pace": ["pace", "relaxed", "moderate", "packed"],
    "group": [
        "who will be joining", "who's joining", "joining you", "travelling with",
        "traveling with", "solo", "partner", "family", "friends", "wife", "husband",
        "kids", "children",
    ],
    "purpose": [
        "purpose of this trip", "kind of trip", "leisure", "adventure",
        "honeymoon", "family vacation", "friends trip",
    ],
    "destination": ["where are you", "heading", "dreaming of", "destination"],
}

_OFF_TOPIC_KEYWORDS: dict[str, list[str]] = {
    # If chips == the pace set, a reply that's actually about budget/money
    # (the exact 2026-07-18 production bug) should trip this.
    "pace": [
        "budget", "₹", "rs.", "inr", "cost", "expense", "breakup", "breakdown",
        "afford", "price", "lakh", "rupee",
    ],
    "group": [
        "budget", "₹", "cost", "expense", "breakup", "breakdown", "pace",
        "relaxed", "packed",
    ],
    "purpose": [
        "budget", "₹", "cost", "expense", "pace", "relaxed", "packed", "group",
        "who's joining", "who will be joining",
    ],
    "destination": [
        "budget", "₹", "cost", "expense", "pace", "relaxed", "packed",
    ],
}


def check_chips_is_list(turn: TurnRecord) -> tuple[bool, str]:
    """ANYA-W-016 equivalent: chips must be a real JSON array, never text."""
    chips = turn.get("chips")
    ok = isinstance(chips, list) and all(isinstance(c, str) for c in chips)
    return ok, "" if ok else f"chips is not a list[str]: {chips!r}"


def check_no_inline_json_leak(turn: TurnRecord) -> tuple[bool, str]:
    """ANYA-W-011/EXT-015 equivalent: reply must never be (or start with)
    raw leaked JSON -- a real observed failure mode where the model's whole
    structured output spills into the user-facing reply text."""
    reply = (turn.get("reply") or "").strip()
    leaked = reply.startswith("{") or '"config_patch"' in reply or '"chips"' in reply
    return (not leaked), "" if not leaked else f"reply looks like leaked JSON: {reply[:120]!r}"


def check_chip_topic_alignment(turn: TurnRecord) -> tuple[bool, str]:
    """The regression check for the 2026-07-18 production bug: if the
    offered chips exactly match a field's canonical set, the reply text
    must not clearly be talking about a DIFFERENT topic (per
    _OFF_TOPIC_KEYWORDS). Catches "budget confirmation reply, pace chips
    underneath" without needing an LLM judge -- this is a structural
    mismatch, not a subjective quality question."""
    chips = turn.get("chips") or []
    reply = (turn.get("reply") or "").lower()
    chip_set = frozenset(chips)
    for field, canonical in _FIELD_CHIP_SETS.items():
        if chip_set == canonical:
            bad_keywords = [kw for kw in _OFF_TOPIC_KEYWORDS.get(field, []) if kw in reply]
            has_target_keyword = any(kw in reply for kw in _TARGET_KEYWORDS.get(field, []))
            if bad_keywords and not has_target_keyword:
                return False, (
                    f"chips are the '{field}' set but reply mentions off-topic "
                    f"keyword(s) {bad_keywords} and never actually asks about "
                    f"'{field}' -- likely a stale/mismatched chip backfill "
                    f"(see 2026-07-18 budget/pace bug)"
                )
    return True, ""


def check_no_stale_chips_for_filled_field(turn: TurnRecord) -> tuple[bool, str]:
    """Reuses the production `_is_stale_chips` helper directly: chips must
    never echo a field's canonical set once CURRENT_STATE says that field
    is already filled."""
    chips = turn.get("chips") or []
    config_after = turn.get("config_after") or {}
    stale = _is_stale_chips(chips, config_after)
    return (not stale), "" if not stale else f"chips {chips!r} are stale for already-filled field(s) in {config_after!r}"


def check_ready_to_generate_is_backed(turn: TurnRecord) -> tuple[bool, str]:
    """_HALLUCINATED_GENERATION_RE-adjacent honesty check: ready_to_generate
    must only be true when every required field is genuinely present."""
    ready = bool(turn.get("ready_to_generate"))
    config_after = turn.get("config_after") or {}
    if not ready:
        return True, ""
    ok = _has_all_required(config_after)
    return ok, "" if ok else f"ready_to_generate=True but _has_all_required() is False for {config_after!r}"


ALL_CHECKS: dict[str, CheckFn] = {
    "chips_is_list": check_chips_is_list,
    "no_inline_json_leak": check_no_inline_json_leak,
    "chip_topic_alignment": check_chip_topic_alignment,
    "no_stale_chips_for_filled_field": check_no_stale_chips_for_filled_field,
    "ready_to_generate_is_backed": check_ready_to_generate_is_backed,
}


def run_all_checks(turn: TurnRecord, checks_to_run: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Runs every registered check against one turn record, or only the
    subset named in `checks_to_run` (see eval/eval_config.json's
    wizard.checks_to_run -- lets a noisy/broken check be disabled without
    editing this file). A check that raises is recorded as a failure with
    the exception text, rather than aborting the whole eval run."""
    results: dict[str, dict[str, Any]] = {}
    names = checks_to_run if checks_to_run is not None else list(ALL_CHECKS)
    for name in names:
        fn = ALL_CHECKS.get(name)
        if fn is None:
            results[name] = {"passed": False, "detail": f"unknown check name {name!r} in checks_to_run"}
            continue
        try:
            passed, detail = fn(turn)
        except Exception as exc:  # noqa: BLE001 -- a broken check must not kill the run
            passed, detail = False, f"check raised {type(exc).__name__}: {exc}"
        results[name] = {"passed": passed, "detail": detail}
    return results
