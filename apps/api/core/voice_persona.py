"""Single source of truth for Anya's TTS voice.

Nothing outside this module may hardcode a Chirp 3: HD voice name, speaking
rate, or audio encoding — see docs/adr/0001-anya-voice-provider.md for how
these values were chosen (5-voice audition across hi-IN/en-IN, Achernar
picked by listening).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VoicePersona:
    voice_name: str  # Chirp 3: HD voice name, e.g. "Achernar"
    speaking_rate: float
    audio_encoding: str  # matches google.cloud.texttospeech.AudioEncoding member name


# Chosen in the Phase 0 audition (docs/adr/0001-anya-voice-provider.md):
# Achernar — Google's own persona descriptor is "Soft" — held its identity
# across hi-IN and en-IN better than Leda/Aoede/Kore/Sulafat on the 6-line
# audition set (plain English, plain Hindi, Hinglish, a ₹-amount line, and
# two everyday replies).
ANYA_VOICE = VoicePersona(
    voice_name="Achernar",
    speaking_rate=1.0,
    # OGG_OPUS is materially smaller than MP3 on Indian mobile networks
    # (docs/adr/0001-anya-voice-provider.md).
    audio_encoding="OGG_OPUS",
)

# Region pinned to the closest GA region to India (docs/adr/0001).
TTS_REGION = "asia-southeast1"

# hi-IN and en-IN are the only two locales Anya's persona needs today.
SUPPORTED_LANGUAGES = ("hi-IN", "en-IN")


def chirp_voice_name(lang: str) -> str:
    """Builds the full `{locale}-Chirp3-HD-{Name}` voice identifier."""
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported TTS language: {lang!r}")
    return f"{lang}-Chirp3-HD-{ANYA_VOICE.voice_name}"


# Every Chirp 3: HD voice tested in the Phase 0 audition mispronounced
# "Anya"/"अन्या" with a short/flat vowel instead of the intended long /ɑː/
# ("aardvark" A). A plain-text respelling was sufficient — no SSML required
# (docs/adr/0001-anya-voice-provider.md, "Pronunciation fix" section).
#
# This substitution is TTS-only: it must be applied to the text sent to the
# synthesis call, never to text shown in the chat UI.
_NAME_RESPELLINGS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAnya\b", re.IGNORECASE), "Aanya"),
    (re.compile(r"अन्या"), "आन्या"),
)


def respell_name_for_speech(text: str) -> str:
    """Applies Anya's name pronunciation fix to TTS-bound text only."""
    for pattern, replacement in _NAME_RESPELLINGS:
        text = pattern.sub(replacement, text)
    return text
