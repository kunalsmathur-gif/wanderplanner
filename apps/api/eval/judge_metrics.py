"""Local LLM-as-judge quality metric for the model-comparison eval
(eval/run_model_comparison.py).

`model_comparison_scoring.py`'s `accuracy_score` is entirely deterministic
(schema validity, day-count match, keyword coverage, budget adherence) --
it cannot tell whether an itinerary actually *reads well*, feels
personalized to the traveller's stated personas/themes/pace, or has a
coherent day-to-day flow (e.g. backtracking across a city, or ignoring a
stated pace preference). Those are exactly the subjective-quality axes the
agents-cli eval skill's `final_response_quality` / `general_quality`
built-in metrics exist for -- this module is a small local equivalent,
using `google-genai` directly (mirrors the scaffolded default pattern:
`genai.Client()` reads GEMINI_API_KEY / ADC).

Judge model is intentionally a fixed, cheap default (not whatever model is
under test) so scores are comparable across candidates -- judging GPT-4o's
output with GPT-4o itself (or, worse, with Gemini vs. GPT-4o inconsistently)
would bias the comparison.
"""
from __future__ import annotations

import asyncio
import json
import re

from core.config import settings

JUDGE_MODEL = "gemini-2.5-flash"

_JUDGE_PROMPT = """You are grading a travel itinerary for quality, NOT correctness (a separate \
deterministic check already covers schema/budget/day-count). Score the itinerary below on three \
axes, each 1-5 (5 = excellent):

  tone: Does the writing sound like a helpful, warm travel planner (not generic/robotic, not \
overly salesy)?
  personalization: Does the itinerary genuinely reflect the traveller's stated preferences \
(personas: {personas}, themes: {themes}, pace: {pace}) rather than a generic city tour?
  coherence: Is the day-to-day flow logical -- no backtracking across the city, activities \
ordered sensibly by time of day, pace consistent with the stated preference?

Traveller context: destination={destination}, group={group}.

Itinerary JSON:
{itinerary_json}

Respond ONLY with a JSON object, no markdown fences, no other text:
{{"tone": <1-5>, "personalization": <1-5>, "coherence": <1-5>, "rationale": "<one sentence>"}}
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def judge_available() -> bool:
    return bool(settings.gemini_api_key) and settings.llm_provider != "mock"


async def judge_itinerary_quality(
    raw: dict, case: dict, trip_config_dict: dict, model: str = JUDGE_MODEL
) -> dict | None:
    """Returns {"tone", "personalization", "coherence", "overall" (0-1 mean
    of the three, normalized), "rationale"} or None if no judge is
    configured (GEMINI_API_KEY unset) or the judge call/parse fails --
    callers must treat None as "unavailable", not as a zero score, so a
    missing key doesn't silently tank a model's aggregate.

    `model` defaults to JUDGE_MODEL but can be overridden by callers reading
    eval/eval_config.json's model_comparison.judge.model, so the judge model
    can be swapped without editing this file."""
    if not judge_available():
        return None

    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        return None

    prompt = _JUDGE_PROMPT.format(
        personas=", ".join(case.get("personas", []) or ["none stated"]),
        themes=", ".join(case.get("themes", []) or ["none stated"]),
        pace=case.get("pace", "moderate"),
        destination=trip_config_dict.get("destination", {}),
        group=trip_config_dict.get("group", {}),
        itinerary_json=json.dumps(raw)[:6000],  # cap: judge cost/latency, not itinerary length itself
    )

    client = google_genai.Client(api_key=settings.gemini_api_key)

    def _call_sync():
        return client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                # NOTE: this installed google-genai SDK version's ThinkingConfig
                # only exposes `include_thoughts`, not `thinking_budget` (unlike
                # the newer SDK extract_trip_chain.py/interest_expansion_chain.py
                # assume) -- so thinking can't be disabled here. Instead, budget
                # generously for gemini-2.5-flash's hidden pre-JSON thinking
                # tokens, which otherwise silently eat the whole cap before any
                # visible JSON is emitted (verified: 300 tokens truncates with
                # zero JSON output; 2048 reliably leaves room for both).
                max_output_tokens=2048,
            ),
        )

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _call_sync)
        parsed = json.loads(_strip_fences(response.text or ""))
        tone = float(parsed["tone"])
        personalization = float(parsed["personalization"])
        coherence = float(parsed["coherence"])
        overall = round(((tone + personalization + coherence) / 3 - 1) / 4, 4)  # 1-5 -> 0-1
        return {
            "tone": tone,
            "personalization": personalization,
            "coherence": coherence,
            "overall": overall,
            "rationale": str(parsed.get("rationale", "")),
        }
    except Exception:  # noqa: BLE001 -- judge is best-effort, never fail the eval run over it
        return None
