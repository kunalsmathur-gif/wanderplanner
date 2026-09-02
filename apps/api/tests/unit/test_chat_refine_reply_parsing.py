"""Regression guard for a live prod bug (2026-09-02): when the chat-refine
LLM's JSON response was malformed or truncated by max_output_tokens, the old
fallback (`reply=raw`) showed the user the raw JSON blob verbatim — braces,
quotes, the `"reply":` key and all — instead of just the conversational text.
`chains.chat_refine_chain._extract_reply_text()` is the fix: it recovers just
the reply string via regex when a full `json.loads()` fails, and only falls
back to a generic apology if even that can't find a `"reply"` field at all.
"""
from __future__ import annotations

from chains.chat_refine_chain import (
    ChatRefineResponse,
    _extract_reply_text,
    _strip_false_regen_progress_claim,
)


class TestExtractReplyText:
    def test_recovers_reply_from_json_truncated_mid_string(self):
        # Exactly the live failure mode: max_output_tokens cut the model off
        # partway through the reply string, before the closing quote/brace.
        raw = (
            '{\n'
            '"reply": "Got it! To make sure you have enough time for both '
            'whale watching and Yala National Park without rushing, I\'ll '
            'regenerate your itinerary to spread these activities across'
        )
        result = _extract_reply_text(raw)
        assert result.startswith("Got it! To make sure you have enough time")
        assert "{" not in result
        assert '"reply"' not in result

    def test_recovers_reply_from_well_formed_but_unparsed_json(self):
        raw = '{"reply": "Sure, updating your pace now.", "action_type": "patch_config"}'
        result = _extract_reply_text(raw)
        assert result == "Sure, updating your pace now."

    def test_unescapes_embedded_quotes_and_newlines(self):
        raw = '{"reply": "Line one.\\nHe said \\"yes\\"."'
        result = _extract_reply_text(raw)
        assert result == 'Line one.\nHe said "yes".'

    def test_falls_back_to_a_generic_message_when_no_reply_field_exists(self):
        raw = '{"action_type": "none", "major_change": false}'
        result = _extract_reply_text(raw)
        assert "{" not in result
        assert '"' not in result or "reply" not in result
        assert len(result) > 0

    def test_never_returns_raw_json_syntax(self):
        """The exact bug: raw JSON braces/keys must never reach the user,
        regardless of which recovery path is taken."""
        malformed_samples = [
            '{"reply": "Absolutely! We can adjust',
            'not json at all',
            '{}',
            '',
        ]
        for raw in malformed_samples:
            result = _extract_reply_text(raw)
            assert not result.strip().startswith("{"), f"leaked raw JSON for input {raw!r}: {result!r}"


class TestStripFalseRegenProgressClaim:
    """Regression guard for a live prod bug (2026-09-02): a user asked 'is it
    done?' after a regeneration was merely proposed (not yet confirmed via
    the client button/typed 'yes'), and the model replied claiming it was
    'now regenerating... this might take a moment... I'll let you know once
    the new itinerary is ready' — while nothing had actually been triggered,
    so no loader ever appeared and the itinerary never changed.
    """

    def test_retracts_exact_live_bug_text(self):
        resp = ChatRefineResponse(
            reply=(
                "My apologies for the confusion! Yes, I'm now regenerating your "
                "trip plan to make sure whale watching and the Yala safari are "
                "on separate days. This might take a moment. I'll let you know "
                "once the new itinerary is ready!"
            ),
            action_type="none",
        )
        result = _strip_false_regen_progress_claim(resp)
        assert "now regenerating" not in result.reply.lower()
        assert "don't actually have visibility" in result.reply

    def test_leaves_legitimate_ask_to_confirm_untouched(self):
        resp = ChatRefineResponse(
            reply="I'll regenerate your itinerary to spread these across different days. Shall I proceed?",
            action_type="regenerate",
            major_change=True,
        )
        result = _strip_false_regen_progress_claim(resp)
        assert result.reply.startswith("I'll regenerate")

    def test_leaves_unrelated_replies_untouched(self):
        resp = ChatRefineResponse(reply="The best time to visit Kerala is Nov-Feb.", action_type="none")
        result = _strip_false_regen_progress_claim(resp)
        assert result.reply == "The best time to visit Kerala is Nov-Feb."
