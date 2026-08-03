"""Unit tests for core/voice_persona.py — Anya's voice config and the
name-pronunciation fix (docs/adr/0001-anya-voice-provider.md).
"""
from __future__ import annotations

import pytest

from core.voice_persona import chirp_voice_name, respell_name_for_speech


class TestChirpVoiceName:
    def test_builds_hi_in_voice_name(self):
        assert chirp_voice_name("hi-IN") == "hi-IN-Chirp3-HD-Achernar"

    def test_builds_en_in_voice_name(self):
        assert chirp_voice_name("en-IN") == "en-IN-Chirp3-HD-Achernar"

    def test_rejects_unsupported_language(self):
        with pytest.raises(ValueError):
            chirp_voice_name("fr-FR")


class TestRespellNameForSpeech:
    def test_respells_anya_case_insensitive(self):
        assert respell_name_for_speech("Hi, I'm Anya!") == "Hi, I'm Aanya!"
        assert respell_name_for_speech("hi, i'm anya!") == "hi, i'm Aanya!"

    def test_respells_hindi_short_a_to_long_aa(self):
        assert respell_name_for_speech("मैं अन्या हूँ") == "मैं आन्या हूँ"

    def test_does_not_touch_unrelated_text(self):
        text = "Let's plan a trip to Goa for 4 days."
        assert respell_name_for_speech(text) == text

    def test_does_not_partially_match_inside_other_words(self):
        # word-boundary guard: must not mangle a name that merely contains "anya"
        assert respell_name_for_speech("Tanya loves Goa") == "Tanya loves Goa"
