"""Tests for core/logging_config.py's redaction filter.

This matters more than it looks: httpx logs full request URLs at INFO, and
several providers pass credentials as query parameters rather than headers
(YouTube's `?key=AIza…` is the live example). Without redaction those land
verbatim in the Railway logs, so each supported provider prefix gets a test.
"""
import logging

from core.logging_config import RedactionFilter, _redact

# Structurally valid but fake — never real credentials.
FAKE_GOOGLE = "AIzaSyB000FakeKeyForRedactionTest_123456"
FAKE_OPENAI = "sk-000FakeOpenAIKeyForRedactionTest123"
FAKE_GROQ = "gsk_000FakeGroqKeyForRedactionTest123"
FAKE_RESEND = "re_000FakeResendKeyForRedactionTest12"


def test_redacts_google_key_in_query_string():
    """The live case: httpx logging a YouTube Data API request URL."""
    line = f"HTTP Request: GET https://www.googleapis.com/youtube/v3/search?key={FAKE_GOOGLE}&part=snippet"
    out = _redact(line)
    assert FAKE_GOOGLE not in out
    assert "[redacted-key]" in out
    # The rest of the URL must survive — redaction shouldn't destroy the log's usefulness.
    assert "youtube/v3/search" in out


def test_redacts_openai_key():
    assert FAKE_OPENAI not in _redact(f"Authorization: Bearer {FAKE_OPENAI}")


def test_redacts_groq_key():
    assert FAKE_GROQ not in _redact(f"key={FAKE_GROQ}")


def test_redacts_resend_key():
    """Added 2026-07-25 alongside the first real Resend key reaching prod."""
    out = _redact(f"Resend send failed with key {FAKE_RESEND}")
    assert FAKE_RESEND not in out
    assert "[redacted-key]" in out


def test_redacts_email_address():
    out = _redact("Password reset requested for traveller@example.com")
    assert "traveller@example.com" not in out
    assert "[redacted-email]" in out


def test_leaves_ordinary_log_lines_untouched():
    line = "Ingested 216 YouTube comments for Edinburgh"
    assert _redact(line) == line


def test_filter_applies_to_formatted_record():
    """The filter must redact the *formatted* message, not just the template —
    args are interpolated first, then blanked."""
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="calling %s with key=%s", args=("youtube", FAKE_GOOGLE), exc_info=None,
    )
    assert RedactionFilter().filter(record) is True
    assert FAKE_GOOGLE not in record.getMessage()
    assert "[redacted-key]" in record.getMessage()
