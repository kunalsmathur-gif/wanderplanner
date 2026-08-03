"""Server-side TTS endpoint for Anya's voice (docs/adr/0001-anya-voice-provider.md).

POST /voice/tts synthesizes the exact same audio bytes for every device,
replacing the OS-delegated `speechSynthesis` voice selection that produced
the "different Anya on every device" bug. See the ADR for full context.

Request flow: reply-signature check -> language/length validation -> Redis
cache -> monthly budget guard -> provider call -> cache write. Any failure
(including a disabled provider or budget breach) returns a distinct,
frontend-recognizable response rather than ever falling back to
`speechSynthesis` — text-only-with-a-notice is the explicit product
decision here, not an oversight.
"""
from __future__ import annotations

import hashlib
import base64
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.config import settings
from core.rate_limit import DEFAULT_RATE_LIMIT, limiter
from core.redis_client import get_cache
from core.reply_signing import verify_reply
from core.tts_budget import record_chars_used, would_exceed_budget
from core.voice_persona import ANYA_VOICE, SUPPORTED_LANGUAGES, respell_name_for_speech
from services.tts.base import (
    TtsError,
    TtsProviderUnavailableError,
    TtsQuotaExceededError,
    TtsUnsupportedLanguageError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days — Anya's stock lines repeat constantly
_AUDIO_MEDIA_TYPES = {"OGG_OPUS": "audio/ogg", "MP3": "audio/mpeg", "LINEAR16": "audio/wav"}

# Error codes the frontend maps to its text-only fallback UI (task
# voice-text-only-fallback) — never to a client-side speechSynthesis retry.
ERROR_PROVIDER_DISABLED = "tts_provider_disabled"
ERROR_BUDGET_EXCEEDED = "tts_budget_exceeded"
ERROR_INVALID_SIGNATURE = "tts_invalid_signature"
ERROR_UNAVAILABLE = "tts_unavailable"


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1)
    lang: str
    sig: str


def _get_provider():
    """Lazily constructed so importing this router never requires TTS
    credentials to be configured — mirrors core/redis_client.py and
    core/qdrant.py's lazy-backend pattern."""
    from services.tts.google_chirp import GoogleChirpProvider

    return GoogleChirpProvider()


_provider = None


def _provider_singleton():
    global _provider
    if _provider is None:
        _provider = _get_provider()
    return _provider


def _cache_key(text: str, lang: str) -> str:
    raw = f"google|{ANYA_VOICE.voice_name}|{lang}|{ANYA_VOICE.speaking_rate}|{text}"
    return "tts:audio:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/voice/tts")
@limiter.limit(DEFAULT_RATE_LIMIT)
async def synthesize_voice(request: Request, body: TtsRequest) -> Response:
    if settings.tts_provider == "off":
        raise HTTPException(status_code=503, detail={"error": ERROR_PROVIDER_DISABLED})

    if body.lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail={"error": "unsupported_language"})

    if len(body.text) > settings.tts_max_input_chars:
        raise HTTPException(status_code=400, detail={"error": "text_too_long"})

    if not verify_reply(body.text, body.sig):
        raise HTTPException(status_code=403, detail={"error": ERROR_INVALID_SIGNATURE})

    cache = get_cache()
    key = _cache_key(body.text, body.lang)
    cached = await cache.get_json(key)
    media_type = _AUDIO_MEDIA_TYPES[ANYA_VOICE.audio_encoding]
    if cached is not None:
        return Response(content=base64.b64decode(cached), media_type=media_type)

    if await would_exceed_budget(len(body.text)):
        logger.warning("TTS monthly character budget would be exceeded — refusing synthesis")
        raise HTTPException(status_code=402, detail={"error": ERROR_BUDGET_EXCEEDED})

    speech_text = respell_name_for_speech(body.text)

    try:
        audio_bytes = await _provider_singleton().synthesize(speech_text, body.lang)
    except TtsUnsupportedLanguageError as e:
        raise HTTPException(status_code=400, detail={"error": "unsupported_language"}) from e
    except TtsQuotaExceededError as e:
        logger.error("TTS provider quota exceeded: %s", e)
        raise HTTPException(status_code=402, detail={"error": ERROR_BUDGET_EXCEEDED}) from e
    except (TtsProviderUnavailableError, TtsError) as e:
        logger.error("TTS synthesis failed: %s", e)
        raise HTTPException(status_code=502, detail={"error": ERROR_UNAVAILABLE}) from e

    await record_chars_used(len(body.text))
    await cache.set_json(key, base64.b64encode(audio_bytes).decode("ascii"), ttl_seconds=_CACHE_TTL_SECONDS)

    return Response(content=audio_bytes, media_type=media_type)
