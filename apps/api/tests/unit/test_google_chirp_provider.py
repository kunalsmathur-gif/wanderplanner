"""Unit tests for services/tts/google_chirp.py — provider error mapping
(docs/adr/0001-anya-voice-provider.md, task tts-backend-tests). The Google
client itself is mocked; only our own error-translation logic is under test.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.tts.base import TtsProviderUnavailableError, TtsUnsupportedLanguageError
from services.tts.google_chirp import GoogleChirpProvider


class TestGoogleChirpProviderSynthesize:
    async def test_rejects_unsupported_language_before_calling_client(self):
        provider = GoogleChirpProvider()
        with pytest.raises(TtsUnsupportedLanguageError):
            await provider.synthesize("hello", "fr-FR")

    async def test_returns_audio_bytes_on_success(self, monkeypatch):
        provider = GoogleChirpProvider()
        fake_response = SimpleNamespace(audio_content=b"fake-audio-bytes")
        mock_client = AsyncMock()
        mock_client.synthesize_speech = AsyncMock(return_value=fake_response)
        monkeypatch.setattr(provider, "_get_client", lambda: mock_client)

        result = await provider.synthesize("Hey! I'm Aanya.", "en-IN")

        assert result == b"fake-audio-bytes"
        mock_client.synthesize_speech.assert_awaited_once()

    async def test_maps_transport_failure_to_provider_unavailable(self, monkeypatch):
        from google.api_core import exceptions as google_exceptions

        provider = GoogleChirpProvider()
        mock_client = AsyncMock()
        mock_client.synthesize_speech = AsyncMock(
            side_effect=google_exceptions.ServiceUnavailable("boom")
        )
        monkeypatch.setattr(provider, "_get_client", lambda: mock_client)

        with pytest.raises(TtsProviderUnavailableError):
            await provider.synthesize("Hey! I'm Aanya.", "en-IN")
