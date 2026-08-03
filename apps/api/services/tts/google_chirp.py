"""Google Cloud TTS Chirp 3: HD provider — first (and currently only)
implementation of TtsProvider (docs/adr/0001-anya-voice-provider.md).

Credentials: Cloud TTS has no API-key auth path, only Application Default
Credentials via a service account (docs/adr/0001, "Credentials" section).
Two ways to supply them, checked in this order:

  1. `GOOGLE_TTS_CREDENTIALS_JSON` — the full service-account JSON as a
     string env var. This is the Railway-friendly path, since Railway's
     filesystem isn't guaranteed persistent across deploys.
  2. `GOOGLE_APPLICATION_CREDENTIALS` — a filesystem path to the JSON key,
     picked up automatically by the client library's default ADC search.
     This is what local dev uses (apps/api/secrets/tts-service-account.json,
     gitignored).
"""
from __future__ import annotations

import json
import logging

from core.config import settings
from core.voice_persona import ANYA_VOICE, TTS_REGION, chirp_voice_name
from services.tts.base import (
    TtsProvider,
    TtsProviderUnavailableError,
    TtsQuotaExceededError,
    TtsUnsupportedLanguageError,
)

logger = logging.getLogger(__name__)

# Chirp 3: HD audio encodings map 1:1 onto AudioEncoding enum member names.
_AUDIO_ENCODING_MAP = {
    "OGG_OPUS": "OGG_OPUS",
    "MP3": "MP3",
    "LINEAR16": "LINEAR16",
}


class GoogleChirpProvider(TtsProvider):
    def __init__(self) -> None:
        self._client = None  # lazily constructed — avoids import-time credential errors

    def _get_client(self):
        if self._client is not None:
            return self._client

        # Imported lazily so a missing/optional dependency doesn't break
        # every other router if TTS isn't configured (mirrors core/qdrant.py
        # and core/redis_client.py's lazy-import pattern).
        from google.cloud import texttospeech
        from google.oauth2 import service_account

        if settings.google_tts_credentials_json:
            info = json.loads(settings.google_tts_credentials_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            self._client = texttospeech.TextToSpeechAsyncClient(
                credentials=credentials,
                client_options={"api_endpoint": f"{TTS_REGION}-texttospeech.googleapis.com"},
            )
        else:
            # Falls back to GOOGLE_APPLICATION_CREDENTIALS / default ADC
            # search — this is the local-dev path.
            self._client = texttospeech.TextToSpeechAsyncClient(
                client_options={"api_endpoint": f"{TTS_REGION}-texttospeech.googleapis.com"},
            )
        return self._client

    async def synthesize(self, text: str, lang: str) -> bytes:
        from google.api_core import exceptions as google_exceptions
        from google.cloud import texttospeech

        try:
            voice_name = chirp_voice_name(lang)
        except ValueError as e:
            raise TtsUnsupportedLanguageError(str(e)) from e

        client = self._get_client()
        voice = texttospeech.VoiceSelectionParams(language_code=lang, name=voice_name)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=getattr(
                texttospeech.AudioEncoding, _AUDIO_ENCODING_MAP[ANYA_VOICE.audio_encoding]
            ),
            speaking_rate=ANYA_VOICE.speaking_rate,
        )
        synthesis_input = texttospeech.SynthesisInput(text=text)

        try:
            response = await client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
        except google_exceptions.ResourceExhausted as e:
            raise TtsQuotaExceededError(str(e)) from e
        except (google_exceptions.GoogleAPIError, ConnectionError) as e:
            logger.error("Google Chirp TTS call failed: %s", e)
            raise TtsProviderUnavailableError(str(e)) from e

        return response.audio_content
