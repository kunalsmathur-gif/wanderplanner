"""Interest → entity expansion (refinement hard-constraints, GTM_STRATEGY §2).

Turns a named interest expressed during refinement ("Harry Potter fan",
"F1 enthusiast") into concrete candidate place names near the destination,
via ONE small Gemini call (same pattern as chains/extract_trip_chain.py).

Candidates are only ever *candidates*: services/poi_pinning.py must verify
each one against ingested OSM POIs / Wikivoyage text before it can become a
pinned constraint — anything this chain hallucinates gets dropped there.

Scale/latency/cost: gemini-2.5-flash, ≤256 output tokens, temperature 0.1,
invoked at most once per refinement message and only when the refine LLM
detected a named interest. Zero calls otherwise.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from core.config import settings
from core.llm_client import track_gemini_usage
from core.prompt_guard import neutralize

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 10

_EXPANSION_SYSTEM_PROMPT = """\
You are a travel place-name expansion assistant. Given a traveller's named
interest and their destination city, list real, specific, visitable places
in or near that destination that serve the interest.

RULES:
- Only places you are confident actually exist. Fewer, real places beat many
  invented ones — every name will be verified against a places database and
  invented names are discarded.
- Every place must specifically serve the stated interest — known FOR the
  interest itself, not merely a popular attraction at the destination. If
  you are unsure whether a place genuinely relates to the interest, leave
  it out; do not pad the list.
- Specific venues/sites only (studios, museums, filming locations, circuits,
  shops, viewpoints) — no whole cities or generic advice. A named district or
  quarter counts ONLY when the district itself is the visitable attraction
  for the interest (e.g. a preserved heritage quarter).
- Use the commonly used English name for each place.
- At most 10 candidates. If the destination has nothing for this interest,
  return an empty list.

RESPONSE FORMAT — respond ONLY with valid JSON, no markdown fences:
{"candidates": ["Place Name One", "Place Name Two"]}
"""

# Deterministic canned expansions for mock/dev mode and offline demos.
_MOCK_EXPANSIONS: dict[str, list[str]] = {
    "harry potter": [
        "Warner Bros. Studio Tour London",
        "Platform 9 3/4 King's Cross",
        "Leadenhall Market",
    ],
    "f1": ["Buddh International Circuit"],
    "formula 1": ["Buddh International Circuit"],
}


def _mock_candidates(interest: str) -> list[str]:
    key = interest.strip().lower()
    for known, places in _MOCK_EXPANSIONS.items():
        if known in key:
            return places
    return []


async def expand_interest_to_candidates(interest: str, destination: str) -> list[str]:
    """One small LLM call: named interest + destination → candidate place names.

    Best-effort: any failure returns [] (the refinement simply proceeds
    without pins) — never raises into the chat-refine path.
    """
    if not interest or not destination:
        return []

    if settings.llm_provider == "mock":
        return _mock_candidates(interest)

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        logger.warning("google-genai not installed; skipping interest expansion")
        return []
    if not settings.gemini_api_key:
        return []

    client = google_genai.Client(api_key=settings.gemini_api_key)
    prompt = (
        f"Interest: {neutralize(interest[:120], context='named interest')}\n"
        f"Destination: {neutralize(destination[:80], context='destination')}"
    )

    for attempt in range(2):
        try:
            def _call_sync():
                return client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_EXPANSION_SYSTEM_PROMPT,
                        temperature=0.1,
                        # 2.5-flash spends max_output_tokens on hidden thinking
                        # BEFORE the visible JSON, so a tight cap returns
                        # truncated JSON (live-verified: 256 died mid-list).
                        # google-genai 1.2.0 has no thinking_budget knob to
                        # turn thinking off — when the dependabot bump to
                        # >=2.x lands, add ThinkingConfig(thinking_budget=0)
                        # and this cap can drop back to ~512.
                        max_output_tokens=2048,
                    ),
                )

            resp = await asyncio.to_thread(_call_sync)
            track_gemini_usage(resp, model="gemini-2.5-flash", purpose="interest_expansion")
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            candidates = data.get("candidates", [])
            return [
                c.strip() for c in candidates
                if isinstance(c, str) and c.strip()
            ][:_MAX_CANDIDATES]
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1)

    logger.warning("interest expansion failed for %r; proceeding without pins", interest)
    return []
