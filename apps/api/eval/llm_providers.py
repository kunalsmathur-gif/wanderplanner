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
}

_PROVIDER_KEY_ATTR = {
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
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


def _call_gemini(model: str, prompt: str) -> tuple[str, int, int]:
    from google import genai
    from google.genai import types as genai_types
    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
    )
    usage = getattr(resp, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0 if usage else 0
    output_tokens = getattr(usage, "candidates_token_count", 0) or 0 if usage else 0
    return resp.text, prompt_tokens, output_tokens


def _call_groq(model: str, prompt: str) -> tuple[str, int, int]:
    from groq import Groq
    client = Groq(api_key=settings.groq_api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    usage = resp.usage
    return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


def _call_openai(model: str, prompt: str) -> tuple[str, int, int]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    usage = resp.usage
    return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


def _call_anthropic(model: str, prompt: str) -> tuple[str, int, int]:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0.4,
        messages=[{"role": "user", "content": prompt + "\n\nRespond with ONLY valid JSON, no markdown fences."}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


_PROVIDER_CALLERS = {
    "gemini": _call_gemini,
    "groq": _call_groq,
    "openai": _call_openai,
    "anthropic": _call_anthropic,
}


def call_model(model: str, prompt: str) -> tuple[str, int, int]:
    """Blocking call — run via loop.run_in_executor from async callers.
    Raises on unknown model id or any provider/SDK error; callers should
    catch broadly, since a red-team payload triggering a provider-side
    refusal/error is itself a valid (safe) outcome to record, not a bug."""
    provider = MODEL_REGISTRY.get(model)
    if provider is None:
        raise ValueError(f"unknown model id {model!r} — not in MODEL_REGISTRY")
    return _PROVIDER_CALLERS[provider](model, prompt)


def strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[1:])
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.split("\n")[:-1])
    return cleaned
