"""Short-lived HMAC signing for assistant replies (task tts-reply-signing,
docs/adr/0001-anya-voice-provider.md).

`/wizard-chat` signs each reply it returns; `/voice/tts` refuses to
synthesize any text whose signature doesn't verify. Without this, the TTS
endpoint would be a free public speech-synthesis API anyone could farm
against the monthly character budget.

Reuses `settings.jwt_secret` rather than introducing a second secret to
manage/rotate — it is already a required, validated-strong secret in
production (core/config.py's `_require_real_secret_in_prod`).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from core.config import settings


def _digest(text: str, expires_at: int) -> str:
    message = f"{expires_at}.{text}".encode("utf-8")
    key = settings.jwt_secret.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def sign_reply(text: str) -> str:
    """Returns a signature token of the form "{expires_at}.{hex_digest}"."""
    expires_at = int(time.time()) + settings.tts_reply_signing_ttl_seconds
    return f"{expires_at}.{_digest(text, expires_at)}"


def verify_reply(text: str, signature: str) -> bool:
    """True iff `signature` was produced by `sign_reply(text)` and has not
    expired. Uses constant-time comparison to avoid timing side-channels."""
    try:
        expires_at_str, digest = signature.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False

    if time.time() > expires_at:
        return False

    expected = _digest(text, expires_at)
    return hmac.compare_digest(expected, digest)
