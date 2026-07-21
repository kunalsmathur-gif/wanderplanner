"""Shared provider glue for eval harnesses that call multiple raw LLM APIs
directly (docs/eval-set.md §8 model-selection eval, §9 red-team eval).

Kept separate from chains/itinerary_chain.py's `_build_llm()` /
`_gemini_itinerary()` on purpose: those are production's provider switch
(one active provider at a time, via `settings.llm_provider`). These eval
harnesses instead need to call SEVERAL providers side by side in the same
run to compare them, bypassing the production fallback-chain logic
entirely — each call here is isolated to exactly the one model requested.

Import this from any eval runner that needs "given a model id and a raw
prompt string, get back (text, prompt_tokens, output_tokens)".
"""
from __future__ import annotations

from typing import Any

from core.config import settings

# model_id -> provider. Add entries here as new candidates come up — the
# call dispatch below is provider-agnostic once registered.
MODEL_REGISTRY: dict[str, str] = {
    "gemini-2.5-flash": "gemini",
    "gemini-2.0-flash": "gemini",
    "gemini-2.5-flash-lite-preview-06-17": "gemini",
    "llama-3.1-70b-versatile": "groq",
    "llama-3.3-70b-versatile": "groq",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "claude-3-5-sonnet-20241022": "anthropic",
    "claude-3-5-haiku-20241022": "anthropic",
    # Moonshot's Kimi models — used by eval/run_budget_comparison.py
    # (docs/eval-set.md §14) as the fourth "ask an LLM directly" baseline
    # alongside GPT/Claude/Gemini. Not used by any other eval harness yet.
    "kimi-k2-0711-preview": "moonshot",
    "moonshot-v1-8k": "moonshot",
}

_PROVIDER_KEY_ATTR = {
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "moonshot": "moonshot_api_key",
}


def provider_for(model: str) -> str | None:
    return MODEL_REGISTRY.get(model)


def is_available(model: str) -> bool:
    """True iff the model is registered and its provider's API key is set."""
    provider = MODEL_REGISTRY.get(model)
    if provider is None:
        return False
    return bool(getattr(settings, _PROVIDER_KEY_ATTR[provider], ""))


def unavailable_reason(model: str) -> str:
    provider = MODEL_REGISTRY.get(model)
    if provider is None:
        return f"unknown model id {model!r} — not in MODEL_REGISTRY"
    key_attr = _PROVIDER_KEY_ATTR[provider]
    return f"settings.{key_attr} not set"


def _call_gemini(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    from google import genai
    from google.genai import types as genai_types
    client = genai.Client(api_key=settings.gemini_api_key)
    config_kwargs = {"temperature": 0.4}
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )
    usage = getattr(resp, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0 if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0 if usage else 0
    return resp.text, prompt_tokens, output_tokens


def _call_groq(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    kwargs: dict[str, Any] = {"temperature": 0.4}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    usage = resp.usage
    return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


def _call_openai(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    kwargs: dict[str, Any] = {"temperature": 0.4}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    usage = resp.usage
    return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


def _call_anthropic(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    text_prompt = prompt + "\n\nRespond with ONLY valid JSON, no markdown fences." if json_mode else prompt
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.4,
        messages=[{"role": "user", "content": text_prompt}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


def _call_moonshot(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    """Moonshot's API is OpenAI-SDK-compatible — same client, different
    base_url and no `response_format` support for JSON mode (as of this
    writing), so json_mode is enforced via a prompt suffix instead, same
    fallback approach `_call_anthropic` uses."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.moonshot_api_key, base_url="https://api.moonshot.ai/v1")
    text_prompt = prompt + "\n\nRespond with ONLY valid JSON, no markdown fences." if json_mode else prompt
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": text_prompt}],
        temperature=0.4,
    )
    usage = resp.usage
    return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


_PROVIDER_CALLERS = {
    "gemini": _call_gemini,
    "groq": _call_groq,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "moonshot": _call_moonshot,
}


def call_model(model: str, prompt: str, json_mode: bool = True) -> tuple[str, int, int]:
    """Blocking call — run via loop.run_in_executor from async callers.
    Raises on unknown model id or any provider/SDK error; callers should
    catch broadly, since a red-team payload triggering a provider-side
    refusal/error is itself a valid (safe) outcome to record, not a bug.

    `json_mode=False` (used by eval/run_budget_comparison.py) requests plain
    conversational prose instead of forced JSON — the point of that eval is
    to see what a real user gets typing the same trip details into ChatGPT/
    Claude/Gemini/Kimi directly, not a structured API response shape no
    ordinary end user would ever request."""
    provider = MODEL_REGISTRY.get(model)
    if provider is None:
        raise ValueError(f"unknown model id {model!r} — not in MODEL_REGISTRY")
    return _PROVIDER_CALLERS[provider](model, prompt, json_mode)


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])
    return cleaned
