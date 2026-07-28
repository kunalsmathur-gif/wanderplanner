"""Bounds and normalisation for user-supplied free text.

Everything typed into the wizard ends up somewhere expensive. A destination
city is interpolated into the Gemini prompt, sent to Nominatim for geocoding,
and used to build an Overpass POI query — three external calls per request,
none of which had any idea how big the string they were given could be. Until
this module existed `DestinationInput.city` was a bare `str`, and every one of
these was accepted by the API and forwarded on: an empty string, whitespace
only, `"🎉🎉🎉"`, `"A" * 10000`, embedded NUL and control characters,
zero-width spaces, an RTL override, and `"Paris\\nIgnore previous
instructions"`.

**This is not the prompt-injection defence.** That is `core/prompt_guard.py`,
which neutralises override phrasing at the prompt boundary and already covers
the trip config (`chains/itinerary_chain.py` neutralises the whole serialised
`TripConfig` before it reaches the model). The exposure this module closes is
different and simpler: unbounded, unshaped free text as a cost, latency and
correctness vector.

Three decisions here are deliberate and worth reading before editing:

* **Over-length input is rejected, never truncated.** Silently trimming
  `"A" * 10000` to 80 characters produces a request that looks valid and
  yields a plausible-but-wrong itinerary — the same failure shape as
  v10.40.0's complete-but-wrong POI pool and v10.40.1's clean-looking
  `0 comments ingested` run log. A 422 with a specific message is the honest
  outcome. Truncation is used in exactly one place, the `dates` key allowlist,
  and it is called out there.

* **Place names must contain at least one letter or digit.** `"🎉🎉🎉"` has a
  non-zero length, so a length check alone passes it; it then normalises to
  nothing useful downstream and produces a fallback itinerary rather than an
  error. `str.isalnum()` is Unicode-aware, so Devanagari, CJK and accented
  names all satisfy this — it rejects emoji-only and punctuation-only input,
  not non-Latin input.

* **ZWJ (U+200D) and ZWNJ (U+200C) survive cleaning; every other format and
  control codepoint is replaced with a space.** Both are category `Cf`, so the
  obvious "strip all control and format characters" rule would take them —
  and they are load-bearing in Devanagari (conjunct control) and in emoji
  sequences. Stripping them would corrupt exactly the Hindi text this
  India-first product most needs to handle. This is the fourth time this
  codebase has been bitten by a character rule written for one script and
  applied to every script; see `core/keyword_match.py`'s docstring for the
  other three. Replacement is a space rather than deletion so that a hidden
  separator can never fuse two tokens into one plausible-looking word
  (`"Paris\\u200bLondon"` becomes `"Paris London"`, not `"ParisLondon"`).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

# --- Length caps -----------------------------------------------------------
# Sized against the longest real values, with headroom: the longest official
# place name in use ("Krung Thep Mahanakhon Amon Rattanakosin …") is ~170
# characters, but every destination this product accepts is an ordinary city
# or country name, and the existing prompt path already truncated destinations
# to 80 (chains/interest_expansion_chain.py).
MAX_CITY_LEN = 80
MAX_COUNTRY_LEN = 80
MAX_IATA_LEN = 8
MAX_LABEL_LEN = 60          # themes, personas, accommodation styles, budget categories
MAX_PURPOSE_LEN = 200
MAX_POI_NAME_LEN = 120
MAX_CURRENCY_LEN = 8
MAX_SEASON_LEN = 40
MAX_CHAT_MESSAGE_LEN = 4000
MAX_EXTRACT_INPUT_LEN = 8000   # "Start Anywhere" free text/URL; the chain then caps at 4000
MAX_SEARCH_QUERY_LEN = 200
MAX_TRIP_CONTEXT_CHARS = 8000  # serialised trip snippet pasted into the chat system prompt

# --- Collection caps -------------------------------------------------------
MAX_CHAT_HISTORY = 100      # chains/chat_chain.py prompts with the last 10; this bounds the body
MAX_HOPS = 5                # matches the frontend store (tripConfigStore.ts) and the model's own comment
MAX_THEMES = 20
MAX_PERSONAS = 20
MAX_STYLE_OPTIONS = 20
MAX_BUDGET_CATEGORIES = 10
MAX_KIDS = 20
MAX_PER_GROUP_FIELD = 30    # adults / seniors / infants / pets, each
MAX_COMPARED_DESTINATIONS = 5   # the UI compares exactly two; this is headroom, not a target

# --- Numeric bounds --------------------------------------------------------
MAX_TRIP_DAYS = 60
# A flexible trip is expressed as a wide start/end *window* with a shorter
# `duration_days` inside it ("sometime in December, about a week" →
# 2026-12-01..2026-12-31 + duration_days=7), so the window is allowed to be far
# longer than the trip itself. A year is the outer bound.
MAX_DATE_WINDOW_DAYS = 366
MAX_BUDGET_AMOUNT = 1_000_000_000
MAX_PREBOOKED_INR = 100_000_000

# Format characters that are meaningful text, not decoration. See the module
# docstring — removing these breaks Devanagari conjuncts and emoji sequences.
_PRESERVED_FORMAT_CHARS = frozenset({"\u200c", "\u200d"})  # ZWNJ, ZWJ

# Control, format, surrogate, private-use and unassigned. Everything a user can
# paste that has no business in a place name or a chat message.
_STRIPPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})

# ISO date, with or without a time suffix — `new Date().toISOString()` on the
# frontend produces the latter, and the backend already reads `start[:10]`
# (core/budget_estimator.py) in anticipation of it.
_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})([T ].*)?$")

# Keys the backend actually reads out of `TripConfig.dates`, across
# chains/, services/ and core/. `start_date`/`end_date` are legacy aliases
# still read by chains/itinerary_chain.py and services/rag_fallback.py.
_ALLOWED_DATE_KEYS = frozenset(
    {"start", "end", "start_date", "end_date", "flexible", "season", "duration_days"}
)


def clean_user_text(value: str, *, allow_newlines: bool = False) -> str:
    """Normalise untrusted text: NFC, no control/format characters, no runs of
    whitespace, no leading or trailing whitespace.

    `allow_newlines` keeps paragraph structure (chat messages, pasted trip
    descriptions) while still collapsing horizontal whitespace and capping
    blank-line runs. Single-line fields get every newline turned into a space.
    """
    text = unicodedata.normalize("NFC", value)

    chars: list[str] = []
    for ch in text:
        if ch in _PRESERVED_FORMAT_CHARS:
            chars.append(ch)
        elif unicodedata.category(ch) in _STRIPPED_CATEGORIES:
            chars.append("\n" if (allow_newlines and ch == "\n") else " ")
        else:
            chars.append(ch)
    text = "".join(chars)

    if allow_newlines:
        text = re.sub(r"[^\S\n]+", " ", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()


def has_alphanumeric(text: str) -> bool:
    """Whether `text` carries any letter or digit in any script.

    `str.isalnum()` is Unicode-aware, so this is true for `"जयपुर"`, `"京都"`
    and `"Zürich"`, and false for `"🎉🎉🎉"`, `"..."` and `"—"`.
    """
    return any(ch.isalnum() for ch in text)


def text_validator(
    *,
    max_length: int,
    field: str,
    required: bool = False,
    allow_newlines: bool = False,
    require_alphanumeric: bool = False,
):
    """Build a Pydantic `BeforeValidator` callable enforcing one field's rules.

    Raises `ValueError` (surfacing as a 422 with the message below) rather than
    coercing, so a rejected value is visible to the caller instead of quietly
    becoming something else.
    """

    def _validate(value: Any) -> str:
        if value is None and not required:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")

        cleaned = clean_user_text(value, allow_newlines=allow_newlines)

        if len(cleaned) > max_length:
            raise ValueError(
                f"{field} must be at most {max_length} characters "
                f"(received {len(cleaned)})"
            )
        if not cleaned:
            if required:
                raise ValueError(f"{field} is required")
            return cleaned
        if require_alphanumeric and not has_alphanumeric(cleaned):
            raise ValueError(f"{field} must contain at least one letter or number")
        return cleaned

    return _validate


def clean_trip_dates(value: Any) -> dict[str, Any]:
    """Validate the shape of `TripConfig.dates`.

    Left as a plain `dict` on purpose — a dozen call sites across `chains/`,
    `services/` and `core/` read it with `.get()`, and converting it to a model
    is a separate change. What this fixes is that none of them could trust what
    they read: `start`/`end` were unbounded strings parsed inside a bare
    `except`, so `"2999-01-01"` silently produced a ~355,000-day trip.
    `chains/itinerary_chain.py::_mock_itinerary` builds one dict per day, so
    that is a memory-exhaustion vector reachable from a single request body.
    """
    if value is None:
        return {"start": None, "end": None, "flexible": False}
    if not isinstance(value, dict):
        raise ValueError("dates must be an object")

    # The one place this module truncates rather than rejects: unknown keys are
    # dropped, not an error. The frontend and the wizard LLM both emit this
    # dict, and an extra key is a harmless additive change that should not fail
    # a user's generation — but it must not reach the prompt either.
    cleaned: dict[str, Any] = {k: v for k, v in value.items() if k in _ALLOWED_DATE_KEYS}

    parsed: dict[str, date] = {}
    for key in ("start", "end", "start_date", "end_date"):
        if key not in cleaned:
            continue
        raw = cleaned[key]
        if raw is None or raw == "":
            cleaned[key] = None
            continue
        if not isinstance(raw, str):
            raise ValueError(f"dates.{key} must be a date string (YYYY-MM-DD)")
        match = _ISO_DATE_RE.match(raw.strip())
        if not match:
            raise ValueError(f"dates.{key} must be a date string (YYYY-MM-DD), got {raw[:40]!r}")
        try:
            parsed[key] = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError as exc:
            raise ValueError(f"dates.{key} is not a real date: {raw[:40]!r}") from exc
        cleaned[key] = raw.strip()

    for start_key, end_key in (("start", "end"), ("start_date", "end_date")):
        start, end = parsed.get(start_key), parsed.get(end_key)
        if start and end:
            span = (end - start).days
            if span < 0:
                raise ValueError(f"dates.{end_key} must not be before dates.{start_key}")
            if span > MAX_DATE_WINDOW_DAYS:
                raise ValueError(
                    f"the window between dates.{start_key} and dates.{end_key} must be at "
                    f"most {MAX_DATE_WINDOW_DAYS} days (received {span})"
                )

    if cleaned.get("duration_days") is not None:
        try:
            days = int(cleaned["duration_days"])
        except (TypeError, ValueError) as exc:
            raise ValueError("dates.duration_days must be a whole number of days") from exc
        if not 1 <= days <= MAX_TRIP_DAYS:
            raise ValueError(
                f"dates.duration_days must be between 1 and {MAX_TRIP_DAYS} (received {days})"
            )
        cleaned["duration_days"] = days

    if "season" in cleaned and cleaned["season"] is not None:
        cleaned["season"] = text_validator(max_length=MAX_SEASON_LEN, field="dates.season")(
            cleaned["season"]
        )

    if "flexible" in cleaned:
        cleaned["flexible"] = bool(cleaned["flexible"])

    return cleaned


def validate_query_param(
    value: str,
    *,
    field: str,
    max_length: int,
    required: bool = True,
    require_alphanumeric: bool = False,
) -> str:
    """Apply the same rules to a query/path parameter as to a body field.

    Pydantic's `ValueError` becomes a 422 automatically in a request body but
    a 500 inside a route handler, so the conversion is explicit here. Routers
    call this instead of hand-rolling guards, which is why they can share the
    body's normalisation (a NUL byte in `?destination=` is stripped exactly as
    it is in `trip_config.destination.city`).
    """
    from fastapi import HTTPException

    try:
        return text_validator(
            max_length=max_length,
            field=field,
            required=required,
            require_alphanumeric=require_alphanumeric,
        )(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- Reusable field types --------------------------------------------------
# `Annotated[str, BeforeValidator(...)]` rather than `Field(max_length=...)`
# so the length is measured *after* normalisation (trailing whitespace and
# stripped control characters shouldn't count against a user's budget) and so
# the error message names the field and the actual length.

CityName = Annotated[
    str,
    BeforeValidator(
        text_validator(
            max_length=MAX_CITY_LEN, field="city", required=True, require_alphanumeric=True
        )
    ),
]

OptionalCityName = Annotated[
    str,
    BeforeValidator(
        text_validator(max_length=MAX_CITY_LEN, field="city", require_alphanumeric=True)
    ),
]

CountryName = Annotated[
    str,
    BeforeValidator(
        text_validator(max_length=MAX_COUNTRY_LEN, field="country", require_alphanumeric=True)
    ),
]

IataCode = Annotated[str, BeforeValidator(text_validator(max_length=MAX_IATA_LEN, field="iata"))]

ShortLabel = Annotated[str, BeforeValidator(text_validator(max_length=MAX_LABEL_LEN, field="value"))]

PurposeText = Annotated[
    str, BeforeValidator(text_validator(max_length=MAX_PURPOSE_LEN, field="purpose"))
]

PoiName = Annotated[
    str, BeforeValidator(text_validator(max_length=MAX_POI_NAME_LEN, field="name"))
]

CurrencyCode = Annotated[
    str, BeforeValidator(text_validator(max_length=MAX_CURRENCY_LEN, field="currency"))
]

FreeFormTripText = Annotated[
    str,
    BeforeValidator(
        text_validator(
            max_length=MAX_EXTRACT_INPUT_LEN,
            field="input",
            required=True,
            allow_newlines=True,
        )
    ),
]

ChatMessageText = Annotated[
    str,
    BeforeValidator(
        text_validator(max_length=MAX_CHAT_MESSAGE_LEN, field="content", allow_newlines=True)
    ),
]

Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]
Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
