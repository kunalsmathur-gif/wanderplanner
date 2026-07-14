"""
Unit tests for routers/travel_tips.py provenance rules (UI/UX audit §1.1,
fixed v10.20): only live-fetched Reddit tips may carry a community source
label or a score; LLM and template tips are always "General tip" with
score=0 and no post_url — enforced in code, not the prompt.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import routers.travel_tips as tt
from routers.travel_tips import (
    GENERAL_TIP_SOURCE,
    _fallback_tips,
    _generate_gemini_tips,
)


def test_fallback_tips_are_honestly_labelled():
    tips = _fallback_tips("Kyoto", 6)
    assert len(tips) == 6
    for tip in tips:
        assert tip.source == GENERAL_TIP_SOURCE
        assert tip.score == 0
        assert tip.post_url == ""


def test_fallback_tips_respect_limit():
    assert len(_fallback_tips("Kyoto", 2)) == 2


def test_prompt_carries_no_community_branding():
    for brand in ("r/travel", "r/solotravel", "TripAdvisor", "Lonely Planet",
                  "Nomadic Matt", "real travelers"):
        assert brand not in tt._TIPS_PROMPT


@pytest.mark.asyncio
async def test_gemini_tips_are_relabelled_even_if_model_fabricates():
    """Even if the model returns community sources and scores, the code
    must strip them — provenance is structural, not prompt-dependent."""
    fabricated = [
        {"title": "Ride the metro", "text_preview": "It's great.",
         "source": "r/travel", "post_url": "https://reddit.com/fake", "score": 999},
        {"title": "Eat local", "text_preview": "Do it.",
         "source": "TripAdvisor", "score": 123},
    ]
    response = MagicMock()
    response.text = json.dumps(fabricated)

    client = MagicMock()
    client.models.generate_content.return_value = response

    with patch.object(tt.settings, "llm_provider", "gemini"), \
         patch.object(tt.settings, "gemini_api_key", "test-key"), \
         patch("google.genai.Client", return_value=client), \
         patch.object(tt, "track_gemini_usage"):
        tips = await _generate_gemini_tips("Kyoto", 2)

    assert len(tips) == 2
    for tip in tips:
        assert tip.source == GENERAL_TIP_SOURCE
        assert tip.score == 0
        assert tip.post_url == ""
