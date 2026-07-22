"""Extract trip intent from a URL or free-form text (blog post, Reddit thread, notes)."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from core.config import settings
from core.llm_client import track_gemini_usage
from core.prompt_guard import wrap_untrusted


class ExtractedTrip(BaseModel):
    destination: str | None = None
    destination_country: str | None = None
    duration_days: int | None = None
    themes: list[str] = []
    budget_inr: int | None = None
    summary: str = ""


_EXTRACT_SYSTEM_PROMPT = """\
You are a travel data extraction assistant. Given a piece of text (from a blog, Reddit, notes or any source), extract structured trip information.

RESPONSE FORMAT — respond ONLY with valid JSON, no markdown fences:
{
  "destination": "City name only (e.g. Bali, Paris). null if not found.",
  "destination_country": "Country name (e.g. Indonesia, France). null if not found.",
  "duration_days": <integer number of days, or null if not mentioned>,
  "themes": ["list", "of", "trip", "themes", "like", "Beach", "Culture", "Food"],
  "budget_inr": <approximate total budget in INR as integer, or null if not mentioned>,
  "summary": "One sentence describing what this trip is about."
}
"""

# SSRF hardening for the "Start Anywhere" URL-fetch feature: only ever fetch
# public HTTP(S) hosts, never follow redirects blindly, and cap what we read.
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_CONTENT_TYPES = ("text/html", "text/plain")
_MAX_REDIRECTS = 3
_MAX_RESPONSE_BYTES = 2_000_000  # 2 MB cap while streaming the response body


class _UnsafeUrlError(Exception):
    pass


def _assert_public_host(url: str) -> tuple[str, str]:
    """Validate scheme + resolve host, rejecting private/loopback/link-local/reserved IPs.

    Returns (hostname, pinned_ip) on success — a single validated public IP the
    caller MUST connect to directly (see `_pinned_get`); raises _UnsafeUrlError
    otherwise.

    Returning the exact IP that was just validated — not only the hostname — is
    what closes the DNS-rebinding (TOCTOU) window. If the caller instead let
    httpx re-resolve the hostname at connect time, an attacker controlling the
    domain's DNS (low TTL) could swap in a private/metadata IP in the gap
    between this check and the actual socket connect. Pinning the connection to
    the IP validated here removes that second, unchecked DNS lookup entirely.
    We still reject the whole URL if *any* resolved address is non-public
    (conservative), and pin the first public one.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise _UnsafeUrlError(f"Unsupported scheme: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise _UnsafeUrlError("URL has no host")

    try:
        addr_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise _UnsafeUrlError(f"Could not resolve host: {host}") from exc

    pinned_ip: str | None = None
    for family, _, _, _, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local  # covers the 169.254.169.254 cloud metadata IP
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise _UnsafeUrlError(f"Refusing to fetch non-public address: {ip}")
        if pinned_ip is None:
            pinned_ip = str(ip)

    if pinned_ip is None:
        raise _UnsafeUrlError(f"Could not resolve host: {host}")

    return host, pinned_ip


async def _pinned_get(client: httpx.AsyncClient, url: str, host: str, ip: str) -> httpx.Response:
    """GET `url` but TCP-connect to the pre-validated literal `ip` instead of
    letting httpx re-resolve `host`. TLS SNI + certificate verification still
    use the real hostname (via httpcore's `sni_hostname` request extension),
    and the HTTP `Host` header is preserved, so virtual-hosted and HTTPS
    origins behave exactly as they would normally — only the second, unchecked
    DNS resolution (the rebinding window) is removed. See `_assert_public_host`.
    """
    parsed = httpx.URL(url)
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"
    pinned_url = parsed.copy_with(host=ip)
    return await client.get(
        pinned_url,
        headers={"User-Agent": "WanderPlanner/1.0", "Host": host_header},
        extensions={"sni_hostname": host},
    )


async def _fetch_url_text(url: str) -> str:
    """Fetch a URL and return plain text (first 6000 chars to stay within token budget).

    Manually walks redirects (instead of `follow_redirects=True`) so every hop
    can be re-validated against the SSRF denylist, and caps response size and
    content-type to avoid abuse as an open proxy/exfiltration channel.
    """
    try:
        current_host, current_ip = _assert_public_host(url)
    except _UnsafeUrlError:
        return ""

    current_url = url
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                resp = await _pinned_get(client, current_url, current_host, current_ip)
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return ""
                    next_url = httpx.URL(current_url).join(location)
                    next_url = str(next_url)
                    try:
                        current_host, current_ip = _assert_public_host(next_url)
                    except _UnsafeUrlError:
                        return ""
                    current_url = next_url
                    continue

                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type and content_type not in _ALLOWED_CONTENT_TYPES:
                    return ""

                raw = resp.content[:_MAX_RESPONSE_BYTES]
                text = raw.decode(resp.encoding or "utf-8", errors="ignore")
                # Strip HTML tags
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                return text[:6000]

            return ""  # too many redirects — bail out rather than loop forever
    except Exception:
        return ""


# Public alias (router imports this name; keep the leading-underscore internal
# name too for any direct callers/tests that still reference it).
fetch_url_text = _fetch_url_text



async def extract_trip_from_text(text: str) -> ExtractedTrip:
    """Use Gemini to extract trip fields from free-form text."""
    try:
        from google import genai as google_genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = google_genai.Client(api_key=settings.gemini_api_key)
    # `text` is either a scraped web page (via _fetch_url_text) or raw
    # user-pasted content — either way it's untrusted and must be fenced off
    # from the instruction itself before going into the prompt.
    untrusted = wrap_untrusted(text[:4000], label="user-provided source text (blog/reddit/notes/webpage)")
    prompt = f"Extract trip info from the following text:\n\n{untrusted}"

    for attempt in range(3):
        try:
            def _call_sync():
                return client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_EXTRACT_SYSTEM_PROMPT,
                        temperature=0.1,
                        # thinking_budget=0 turns off 2.5-flash's hidden
                        # pre-JSON thinking (same fix as interest_expansion_chain.py)
                        # so the token cap covers only the visible JSON output.
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                        max_output_tokens=512,
                    ),
                )

            resp = await asyncio.to_thread(_call_sync)
            track_gemini_usage(resp, model="gemini-2.5-flash", purpose="extract_trip")
            raw = (resp.text or "").strip()
            # Strip possible markdown fences
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            return ExtractedTrip(**data)
        except Exception:
            if attempt == 2:
                break
            await asyncio.sleep(1)

    return ExtractedTrip(summary="Could not extract trip details from this content.")
