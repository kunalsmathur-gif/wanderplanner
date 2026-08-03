"""Unit tests for core/reply_signing.py — the HMAC gate that stops
/voice/tts being farmed as a free public TTS API
(docs/adr/0001-anya-voice-provider.md, task tts-reply-signing).
"""
from __future__ import annotations

import time

from core.reply_signing import sign_reply, verify_reply


class TestSignAndVerify:
    def test_valid_signature_verifies(self):
        text = "Hey! I'm Aanya, your travel planner."
        sig = sign_reply(text)
        assert verify_reply(text, sig) is True

    def test_signature_rejects_tampered_text(self):
        text = "Hey! I'm Aanya, your travel planner."
        sig = sign_reply(text)
        assert verify_reply("Something else entirely", sig) is False

    def test_signature_rejects_malformed_token(self):
        assert verify_reply("any text", "not-a-real-signature") is False

    def test_signature_rejects_empty_string(self):
        assert verify_reply("any text", "") is False

    def test_expired_signature_is_rejected(self, monkeypatch):
        text = "Hey! I'm Aanya, your travel planner."
        sig = sign_reply(text)
        # Jump the clock forward past the TTL.
        future = time.time() + 3600
        monkeypatch.setattr(time, "time", lambda: future)
        assert verify_reply(text, sig) is False
