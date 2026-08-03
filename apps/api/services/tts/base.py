"""Provider-agnostic TTS interface.

Kept separate from any specific vendor SDK so the provider can be swapped
(e.g. to Sarvam, per docs/adr/0001-anya-voice-provider.md) without touching
the router, cache, budget guard, or frontend.
"""
from __future__ import annotations

from typing import Protocol


class TtsError(Exception):
    """Base class for all TTS provider failures."""


class TtsQuotaExceededError(TtsError):
    """The underlying provider itself reports quota/rate-limit exhaustion —
    distinct from our own budget guard (core/tts_budget.py), which is meant
    to trip *before* this ever happens."""


class TtsUnsupportedLanguageError(TtsError):
    """Requested language isn't one of the two Anya supports today."""


class TtsProviderUnavailableError(TtsError):
    """Transport-level failure (network, auth, 5xx) talking to the provider."""


class TtsProvider(Protocol):
    async def synthesize(self, text: str, lang: str) -> bytes:
        """Synthesizes `text` in `lang`, returning encoded audio bytes.

        Raises a `TtsError` subclass on failure. Callers must not assume any
        particular audio format — this is dictated by voice_persona.ANYA_VOICE.
        """
        ...
