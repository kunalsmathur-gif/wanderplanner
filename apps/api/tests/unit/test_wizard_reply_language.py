"""Anya replies in the user's language; the machine-readable fields stay English.

Two things are covered here.

**The prompt rule** (section 3a of ``WIZARD_SYSTEM_PROMPT``). Section 3 has
always handled Hinglish *input* — "Mumbai se Bali 7 days mein" — but said
nothing about output, so every reply came back in English regardless of what
the user wrote. The rule added alongside voice-mode Hindi support says: mirror
the user in ``reply``, and *only* in ``reply``.

**That the reply post-processors do not destroy Devanagari.** This is the part
worth having tests for. Every one of these helpers was written when the reply
was guaranteed to be English, and this codebase has now shipped the same class
of bug five times — a character rule written for one script and applied to
every script (``core/keyword_match.py``, ``core/validation.py``, and the
text-to-speech allowlist in ``apps/web/lib/voice.ts``). These tests pin the
current, verified-safe behaviour so the next edit to a regex here has to
notice Hindi exists.
"""
from __future__ import annotations

from chains.wizard_chat_chain import (
    WIZARD_SYSTEM_PROMPT,
    _decode_stray_unicode_escapes,
    _strip_emoji,
    _strip_leaked_reasoning,
    _strip_leaked_schema_tail,
    _strip_trailing_json_artifacts,
)

# A plausible Anya turn in Hindi: statement, danda, question mark.
HINDI_REPLY = "गोवा बहुत सुंदर है। आप कब जाना चाहेंगे?"


# --- The prompt rule -------------------------------------------------------


class TestReplyLanguageRule:
    def test_prompt_tells_anya_to_mirror_the_user_language(self):
        assert "3a. REPLY LANGUAGE" in WIZARD_SYSTEM_PROMPT

    def test_prompt_covers_devanagari_and_roman_hinglish_separately(self):
        # Roman-script Hinglish must not be answered in Devanagari: a user
        # typing on a QWERTY keyboard cannot easily reply in kind.
        assert "Devanagari Hindi" in WIZARD_SYSTEM_PROMPT
        assert "Roman-script Hinglish" in WIZARD_SYSTEM_PROMPT

    def test_prompt_scopes_the_rule_to_the_reply_field(self):
        assert "APPLIES TO `reply` ONLY" in WIZARD_SYSTEM_PROMPT

    def test_prompt_keeps_chips_in_english(self):
        # apps/web/components/wizard/LLMWizard.tsx classifies chip groups by
        # matching English keywords, so a translated chip does not fail — it
        # silently turns a multi-select group into single-select.
        assert "`chips` — ALWAYS English" in WIZARD_SYSTEM_PROMPT

    def test_prompt_keeps_config_patch_place_names_in_english(self):
        # A destination string is a database key: it is geocoded, ingested and
        # cached under its English name, so "गोवा" would become a second,
        # unrelated destination and trigger a redundant cold-start ingestion
        # of data already held for "Goa".
        assert "`config_patch` — ALWAYS English" in WIZARD_SYSTEM_PROMPT
        assert '"city": "Goa"' in WIZARD_SYSTEM_PROMPT

    def test_prompt_shows_a_worked_hindi_example(self):
        assert "बिल्कुल" in WIZARD_SYSTEM_PROMPT


# --- Devanagari survives the reply pipeline --------------------------------


class TestDevanagariSurvivesPostProcessing:
    def test_leaked_reasoning_stripper_leaves_a_hindi_reply_alone(self):
        # Pass 1 looks for English warm openers after an ASCII sentence end;
        # pass 2 splits on [.!?], which a Hindi sentence terminated by a danda
        # never matches. Both degrade to "return unchanged" — the safe
        # direction — rather than truncating at the wrong boundary.
        assert _strip_leaked_reasoning(HINDI_REPLY) == HINDI_REPLY

    def test_leaked_reasoning_stripper_still_works_on_english_before_hindi(self):
        # The reasoning a model leaks is English-shaped even when the reply is
        # not, because it reasons about our English field names.
        leaked = f"I need to parse this and update the budget field. {HINDI_REPLY}"
        assert _strip_leaked_reasoning(leaked) == HINDI_REPLY

    def test_schema_tail_stripper_leaves_a_hindi_reply_alone(self):
        assert _strip_leaked_schema_tail(HINDI_REPLY) == HINDI_REPLY

    def test_schema_tail_stripper_still_cuts_a_leak_after_hindi(self):
        leaked = f'{HINDI_REPLY}", "chips": [], "config_patch": {{}}'
        assert _strip_leaked_schema_tail(leaked) == HINDI_REPLY

    def test_trailing_artifact_stripper_keeps_the_danda(self):
        # The danda is the Devanagari full stop. Dropping it runs sentences
        # together when the reply is read aloud.
        assert _strip_trailing_json_artifacts("गोवा सुंदर है।") == "गोवा सुंदर है।"

    def test_trailing_artifact_stripper_still_cuts_json_debris(self):
        assert _strip_trailing_json_artifacts('गोवा सुंदर है।",') == "गोवा सुंदर है।"

    def test_unicode_escape_decoder_handles_devanagari(self):
        # Devanagari sits in the BMP, so it arrives as ordinary \\uXXXX escapes
        # on the plain-text fallback path and decodes like ₹ already does.
        assert _decode_stray_unicode_escapes("\\u0917\\u094b\\u0935\\u093e") == "गोवा"

    def test_emoji_stripper_keeps_devanagari_letters(self):
        # Scoped to chip-tap lookups, never the reply. It does strip ZWJ, which
        # is meaningful in Devanagari conjuncts — harmless only because its
        # output feeds an exact-match comparison against English chip labels,
        # where a mangled Hindi string correctly matches nothing. Do not reuse
        # it on user-visible text.
        assert _strip_emoji("गोवा 🌴") == "गोवा "
