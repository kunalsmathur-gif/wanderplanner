# ADR 0001: Anya's voice provider and voice selection

- **Status:** Accepted
- **Date:** 2026-08-03

## Context

Anya's persona is a young Indian woman, but her voice in production was whatever the user's
device happened to have installed. `apps/web/hooks/useVoice.ts` called
`window.speechSynthesis.speak()`, and `apps/web/lib/voice.ts` tried to guess gender from OS voice
*names* (`FEMALE_VOICE_TOKENS` / `MALE_VOICE_TOKENS`), because the Web Speech API exposes no
gender field and delegates voice selection entirely to the OS.

This produced three confirmed production bugs:

- **Male voice on some devices** — the curated name lists missed whatever voice that device
  shipped, scoring "unknown" and falling through to platform order.
- **English voice reading Hindi text on some devices** — no `hi-IN` voice installed at all, so
  `pickVoice` returned null and the platform default read Devanagari with an English engine.
- **A different Anya on every device** — even in the best case, `hi-IN-Swara` (Windows), `Lekha`
  (Apple), and "Google हिन्दी" (Android) are three unrelated people.

The root cause is architectural: **no amount of client-side heuristics can produce a uniform
persona** when the OS owns voice selection. The fix is to synthesize Anya's audio server-side and
ship the same bytes to every device.

Scope decisions confirmed with the user going in:

| Decision | Choice |
| --- | --- |
| Scope | TTS now; STT is a clearly-marked future phase, planned but not built |
| Budget | Free tier first; ~$10–20/month acceptable as headroom |
| Failure / quota-exhausted behaviour | Text-only with a small notice — never let an off-persona voice be heard |
| GCP billing account | Acceptable to create |

## Options considered

| Provider | hi-IN + en-IN, same voice name | Female | Free tier (verified) | Paid | Verdict |
| --- | --- | --- | --- | --- | --- |
| **Google Cloud TTS — Chirp 3: HD** | ✅ same 30 named voices across all 53 locales | ✅ 14 female | ✅ 1M chars/month | $30 / 1M chars | **Chosen** |
| Sarvam AI (Bulbul) | ⚠️ markets same-speaker-across-Indic-languages | ✅ anushka, manisha, vidya | ⚠️ unverified — docs/pricing return HTTP 403 to automated fetches | unknown | Deferred — not evaluated this round, may revisit if Chirp 3: HD identity assumption breaks in practice |
| Azure Neural TTS (F0) | ❌ hi-IN and en-IN are different people | ✅ | ✅ ~500k chars/month | ~$16 / 1M | Rejected — fails the core requirement |
| Gemini Live API | ⚠️ voices not Indian-tuned | ⚠️ | ✅ AI Studio | ~$0.037/min | Rejected — wrong shape (speech-to-speech, tied to an LLM turn) |
| `edge-tts` (unofficial) | ❌ different identities | ✅ | free | — | Rejected — reverse-engineers a Microsoft endpoint against its ToS, and its Hindi/English voices are different people anyway |
| Kokoro / Piper / XTTS / MMS | ❌ | — | free | — | Rejected — no cross-language identity, or no Hindi, or non-commercial, or abandoned |
| AI4Bharat IndicF5 | ❌ no English at all | ✅ | free | — | Rejected — Hindi-only, needs GPU |
| Bhashini (GoI) | ❌ no persona guarantee | ✅ | free | — | Rejected — uptime risk, noted only as a curiosity |

### ⚠️ "Voxilica" does not exist

An earlier recommendation for a provider called "Voxilica" was investigated and found to be
false: `voxilica.com` resolves to a Namecheap domain-parking page — no product, no API, no
company, no docs. It was most likely a hallucinated recommendation from another AI tool. Recorded
here so it is not re-proposed.

## Decision

Use a **provider-agnostic server-side TTS service** in the FastAPI backend, implemented first
with **Google Cloud TTS — Chirp 3: HD**, voice **Achernar** ("Soft" per Google's published voice
descriptors), region `asia-southeast1`.

```
LLMWizard.tsx
  └─ useVoice.speakReply(text, replySig)
       └─ POST /voice/tts { text, lang, sig }        ← same bytes for every device
            ├─ HMAC check    — only speaks text Anya actually generated
            ├─ rate limit    — slowapi, already in the stack
            ├─ Redis cache   — sha256(provider|voice|lang|rate|text)
            ├─ budget guard  — monthly char counter, hard ceiling < 1M
            └─ TtsProvider (Protocol)
                 ├─ GoogleChirpProvider   ← first implementation
                 └─ SarvamProvider        ← only if Chirp 3: HD identity assumption breaks
       └─ HTMLAudioElement.play(blob)     ← replaces speechSynthesis.speak()
```

Provider choice is deliberately kept behind a `TtsProvider` interface: if Chirp 3: HD's cross-locale
identity assumption turns out to be wrong in practice, swapping in Sarvam touches only the
provider implementation, not the router, cache, budget guard, or frontend.

### Voice selection

Auditioned 5 candidate female voices (Leda, Aoede, Kore, Sulafat, Achernar) across `hi-IN` and
`en-IN`, using 6 real Anya-style lines — plain English, plain Hindi, a Hinglish code-switched
line, a ₹-amount line, and two everyday replies — synthesized via a throwaway script
(`google-cloud-texttospeech`, session workspace, not committed to the repo).

Google's own persona descriptors for these 30 Chirp 3: HD / Gemini voice names (from
`ai.google.dev/gemini-api/docs/speech-generation`; Cloud TTS's own docs list only name + gender,
no persona text):

| Voice | Persona | Gender |
| --- | --- | --- |
| Kore | Firm | Female |
| Leda | Youthful | Female |
| Aoede | Breezy | Female |
| **Achernar** | **Soft** | Female |
| Sulafat | Warm | Female |

**Achernar** was chosen after listening to all 5 candidates back-to-back in both locales.

### Pronunciation fix: "Anya" → "Aanya"

All 5 candidate voices, in both `hi-IN` and `en-IN`, mispronounced "Anya" with a short/flat vowel
instead of the intended long `/ɑː/` ("aardvark" A). Tested 9 fix variants on Achernar (Leda used
for the initial exploratory pass): plain-text respelling, SSML `<sub alias="...">`, and SSML
`<phoneme>` with both IPA and X-SAMPA notation, at multiple candidate spellings ("Aanya", "Arnya",
"Ahn-ya").

**Result:** a plain-text respelling was sufficient — no SSML required.

| Language | Displayed text | Text sent to TTS |
| --- | --- | --- |
| English | Anya | **Aanya** |
| Hindi | अन्या | **आन्या** |

This must be applied as a substitution pass on the TTS-bound text only, immediately before the
synthesis call (regex-replace, case-insensitive for the Latin form) — the chat-display text is
untouched. This belongs alongside `sanitiseForSpeech()`'s other TTS-only text transforms, not in
the reply-generation path.

### Credentials

Cloud TTS has **no API-key auth path** — it requires Application Default Credentials via a
service account. Reused the existing GCP project (already hosting the YouTube Data API key), and
created a new dedicated service account:

- `anya-tts-service@wanderplanner-503017.iam.gserviceaccount.com`
- Role: **Cloud Text-to-Speech User**
- JSON key stored locally at `apps/api/secrets/tts-service-account.json` (gitignored via
  `apps/api/secrets/` in `.gitignore` — this directory must never be committed)
- Production (Railway): the JSON contents will need to be loaded from an env var
  (e.g. `GOOGLE_TTS_CREDENTIALS_JSON`) via `service_account.Credentials.from_service_account_info`,
  since Railway's filesystem is not guaranteed persistent — this is heavier setup than the
  existing `GEMINI_API_KEY` pattern and is called out for Phase 1 implementation.

## Consequences

- Same Achernar voice, same bytes, on every device and OS — the bug this ADR exists to fix is
  closed for TTS.
- `pickVoice`, `genderScore`, `FEMALE_VOICE_TOKENS` / `MALE_VOICE_TOKENS`, `hasVoiceForLang`, and
  `missingVoiceMessage` become dead code to remove in Phase 2 (Frontend swap).
- `sanitiseForSpeech()` stays, and gains one more responsibility: the Anya name-respelling pass.
- Service-account credential management is now part of the deploy surface; document the Railway
  env var setup in the deployment runbook when Phase 1 lands.
- Sarvam remains unverified and untried. If Chirp 3: HD's per-locale voice identity ever proves
  inconsistent in wider use (beyond this 6-line audition), Sarvam is the documented fallback to
  evaluate next — not Azure, not `edge-tts`.

## Phase 2 (frontend hookup): shipped

`useVoice.ts`'s `speakReply()` now calls the real `/api/voice/tts` endpoint (via `speakViaServer()`)
whenever the caller threads through `res.reply_sig` from `/api/wizard-chat` — this is now the only
call site (`LLMWizard.tsx`) and is the sole production path. The old `window.speechSynthesis`
branch is kept **only** as a defensive fallback for the should-not-happen case of a missing
signature (e.g. server-side signing itself failing); it is deliberately not treated as a second
supported voice, and any `/voice/tts` failure surfaces a text-only notice — it never falls back to
`speechSynthesis`, since that fallback is the exact "different Anya on every device" bug this ADR
exists to close.

Two real bugs were found and fixed while wiring this up, both worth recording so they aren't
reintroduced:

1. **FastAPI/Pydantic forward-ref bug (root cause of every real `/voice/tts` call 422'ing).**
   `routers/voice.py` had `from __future__ import annotations` while defining the `TtsRequest`
   `BaseModel` in the same module. With FastAPI 0.111.0 + Pydantic 2.13.4, this broke FastAPI's
   dependant analysis, silently downgrading `body: TtsRequest` to a `Query` parameter instead of a
   request body. Fixed by removing the future-annotations import from `voice.py` only — other
   routers keep it safely because their body models are imported from elsewhere, not defined
   in-file.
2. **Local ADC credentials bug (local dev only, not production).** `pydantic-settings` loads
   `.env` values into the app's `Settings` object, but never exports them to real `os.environ` —
   Google's `google.auth.default()` reads `GOOGLE_APPLICATION_CREDENTIALS` straight from
   `os.environ`, so a `.env`-only value was invisible to it. Fixed by adding an explicit
   `google_application_credentials` field to `Settings` and having `google_chirp.py` load the
   service-account file directly via `service_account.Credentials.from_service_account_file(...)`
   instead of relying on bare ADC discovery. Railway's production credentials path
   (`GOOGLE_TTS_CREDENTIALS_JSON`, parsed straight from an env var) was unaffected by this bug.

Verified end-to-end against a local server: `/api/wizard-chat` → signed `reply_sig` →
`/api/voice/tts` → 200 OK, valid Ogg Opus/Achernar audio. `pickVoice`, `genderScore`,
`FEMALE_VOICE_TOKENS` / `MALE_VOICE_TOKENS`, `hasVoiceForLang`, and `missingVoiceMessage` remain in
place for the defensive fallback path rather than being removed, since that path is still reachable
and covered by tests.
