"""Closed-set field normalisation (pace / scope / crowd_preference / destination_mode).

These four were left as free-text `ShortLabel`s by v10.43.0's validation pass,
deliberately: they are populated from the wizard LLM's `config_patch`, so a bare
`Literal` would have turned a casing mismatch into a hard 422 mid-conversation.
Normalising first is what makes the `Literal` safe, and these tests pin both
halves — the canonicalisation *and* the fact that it never raises.

Both directions matter here. The tempting simplification is to treat an
unrecognised value as an error; the tests below assert it falls back instead,
because the caller who pays for a 422 is the user and the party who got it
wrong is our own prompt.
"""
from __future__ import annotations

import logging

import pytest

from core.validation import CHOICE_FIELDS, normalise_choice_fields
from models.trip import TripConfig

# --- Canonical values pass through unchanged -------------------------------

@pytest.mark.parametrize(
    "field,value",
    [
        (field, value)
        for field, rules in CHOICE_FIELDS.items()
        for value in rules["allowed"]
    ],
)
def test_canonical_values_are_untouched(field: str, value: str):
    assert normalise_choice_fields({field: value})[field] == value


# --- The three ways an LLM realistically deviates --------------------------

@pytest.mark.parametrize(
    "field,given,expected",
    [
        # Casing — the exact case named in the TODO as the reason for deferral.
        ("pace", "Moderate", "moderate"),
        ("pace", "RELAXED", "relaxed"),
        ("scope", "International", "international"),
        ("crowd_preference", "Offbeat", "offbeat"),
        ("destination_mode", "Fixed", "fixed"),
        # Decoration: separators, punctuation, stray whitespace.
        ("crowd_preference", "off-beat", "offbeat"),
        ("crowd_preference", "Off Beat!", "offbeat"),
        ("crowd_preference", "off_the_beaten_path", "offbeat"),
        ("pace", "  packed  ", "packed"),
        ("destination_mode", "multi-city", "country"),
        # Synonyms.
        ("pace", "slow", "relaxed"),
        ("pace", "fast", "packed"),
        ("scope", "abroad", "international"),
        ("scope", "national", "domestic"),
        ("crowd_preference", "hidden gems", "offbeat"),
        ("crowd_preference", "popular", "touristy"),
        ("destination_mode", "undecided", "exploring"),
        ("destination_mode", "not sure", "exploring"),
    ],
)
def test_loose_values_are_canonicalised(field: str, given: str, expected: str):
    assert normalise_choice_fields({field: given})[field] == expected


def test_moderate_means_different_things_in_different_fields():
    """`"moderate"` is a canonical `pace` and an alias for `crowd_preference:
    balanced`. This is exactly why the alias maps are per-field and must not be
    merged into one — a shared map would silently make one of these wrong."""
    assert normalise_choice_fields({"pace": "moderate"})["pace"] == "moderate"
    assert (
        normalise_choice_fields({"crowd_preference": "moderate"})["crowd_preference"]
        == "balanced"
    )


# --- Unrecognised input falls back, loudly, instead of raising -------------

@pytest.mark.parametrize(
    "field,given,expected_default",
    [
        ("pace", "supersonic", "moderate"),
        ("scope", "interplanetary", "international"),
        ("crowd_preference", "vibes", "balanced"),
        ("destination_mode", "whatever", "fixed"),
    ],
)
def test_unknown_values_fall_back_to_the_default(field, given, expected_default):
    assert normalise_choice_fields({field: given})[field] == expected_default


def test_unknown_value_is_logged_so_a_missing_alias_is_discoverable(caplog):
    """The fallback is the deliberate exception to this codebase's "reject,
    never coerce" rule, so the WARNING is what keeps it from being silent."""
    with caplog.at_level(logging.WARNING):
        normalise_choice_fields({"pace": "supersonic"})
    assert any("supersonic" in r.message % r.args for r in caplog.records)


@pytest.mark.parametrize("junk", [None, 42, [], {}, True])
def test_non_string_values_never_raise(junk):
    """A `config_patch` is parsed straight out of model JSON, so the value can
    be any JSON type — none of them should be able to fail a user's request."""
    assert normalise_choice_fields({"pace": junk})["pace"] == "moderate"


# --- Absent keys stay absent ----------------------------------------------

def test_absent_fields_are_not_filled_in():
    """This normalises what the model sent. Filling in defaults here would make
    a patch claim the user chose a pace they were never asked about, and the
    wizard's completeness check reads the merged config to decide what to ask."""
    patch = normalise_choice_fields({"purpose": "leisure"})
    assert patch == {"purpose": "leisure"}
    assert "pace" not in patch


def test_other_keys_pass_through_untouched():
    patch = normalise_choice_fields(
        {"pace": "Slow", "destination": {"city": "Jaipur"}, "budget": {"amount": 50000}}
    )
    assert patch["pace"] == "relaxed"
    assert patch["destination"] == {"city": "Jaipur"}
    assert patch["budget"] == {"amount": 50000}


def test_empty_patch_is_returned_as_is():
    assert normalise_choice_fields({}) == {}


def test_input_patch_is_not_mutated():
    original = {"pace": "Moderate"}
    normalise_choice_fields(original)
    assert original == {"pace": "Moderate"}, "caller's dict must not be rewritten in place"


# --- The model layer: Literal is now safe ---------------------------------

def test_trip_config_accepts_loose_values_and_stores_canonical_ones():
    config = TripConfig(
        pace="Moderate",
        scope="Abroad",
        crowd_preference="off-beat",
        destination_mode="undecided",
    )
    assert config.pace == "moderate"
    assert config.scope == "international"
    assert config.crowd_preference == "offbeat"
    assert config.destination_mode == "exploring"


def test_trip_config_does_not_422_on_an_unknown_choice():
    """The whole reason these stayed free-text. A model emitting something
    unmapped must not fail the generate call."""
    config = TripConfig(pace="whatever the model said")
    assert config.pace == "moderate"


def test_trip_config_defaults_are_unchanged():
    config = TripConfig()
    assert config.pace == "moderate"
    assert config.scope == "international"
    assert config.crowd_preference == "balanced"
    assert config.destination_mode == "fixed"


def test_every_alias_target_is_a_real_canonical_value():
    """Guards against a typo in an alias map silently producing a value that
    the `Literal` would then reject at the model layer."""
    from core.validation import (
        _CROWD_PREFERENCE_ALIASES,
        _DESTINATION_MODE_ALIASES,
        _PACE_ALIASES,
        _SCOPE_ALIASES,
    )

    for field, aliases in (
        ("pace", _PACE_ALIASES),
        ("scope", _SCOPE_ALIASES),
        ("crowd_preference", _CROWD_PREFERENCE_ALIASES),
        ("destination_mode", _DESTINATION_MODE_ALIASES),
    ):
        allowed = CHOICE_FIELDS[field]["allowed"]
        for alias, target in aliases.items():
            assert target in allowed, f"{field}: alias {alias!r} → unknown {target!r}"


def test_no_alias_shadows_a_canonical_value_of_its_own_field():
    """An alias keyed on a canonical value of the same field would be dead code
    at best (the canonical check runs first) and a contradiction at worst."""
    from core.validation import (
        _CROWD_PREFERENCE_ALIASES,
        _DESTINATION_MODE_ALIASES,
        _PACE_ALIASES,
        _SCOPE_ALIASES,
    )

    for field, aliases in (
        ("pace", _PACE_ALIASES),
        ("scope", _SCOPE_ALIASES),
        ("crowd_preference", _CROWD_PREFERENCE_ALIASES),
        ("destination_mode", _DESTINATION_MODE_ALIASES),
    ):
        allowed = CHOICE_FIELDS[field]["allowed"]
        shadowed = [a for a in aliases if a in allowed]
        assert not shadowed, f"{field}: alias keys shadow canonical values {shadowed}"


def test_alias_keys_are_already_in_normalised_form():
    """Lookup happens after casefolding and separator collapsing, so an alias
    key carrying uppercase or a hyphen could never be reached."""
    from core.validation import (
        _CROWD_PREFERENCE_ALIASES,
        _DESTINATION_MODE_ALIASES,
        _PACE_ALIASES,
        _SCOPE_ALIASES,
        _SEPARATOR_RUN_RE,
    )

    for aliases in (
        _PACE_ALIASES,
        _SCOPE_ALIASES,
        _CROWD_PREFERENCE_ALIASES,
        _DESTINATION_MODE_ALIASES,
    ):
        for alias in aliases:
            normalised = _SEPARATOR_RUN_RE.sub(" ", alias.casefold()).strip()
            assert alias == normalised, f"unreachable alias key {alias!r} (would need {normalised!r})"
