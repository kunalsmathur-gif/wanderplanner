"""Structured logging setup with basic PII redaction.

Replaces scattered `print()` calls (which are unstructured, can't be
filtered/shipped to a log aggregator, and risk leaking sensitive-looking
data — destination names, trip details, raw exception text) with stdlib
`logging` configured to emit single-line JSON records and redact common
PII/secret patterns before they ever reach a log sink.

See docs/scaling-tech-challenges.md, Security Vulnerabilities #8.
"""
from __future__ import annotations

import json
import logging
import re
import sys

from core.config import settings

# Patterns redacted from every log record message, regardless of logger/level.
# Conservative on purpose: today there are no user accounts, but this must
# already be in place before email/PII fields are added (doc's own guidance).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_APIKEY_RE = re.compile(
    r"\b(AIza[0-9A-Za-z_\-]{10,}"      # Google (YouTube Data API, Maps)
    r"|sk-[A-Za-z0-9]{10,}"            # OpenAI
    r"|gsk_[A-Za-z0-9]{10,}"           # Groq
    r"|re_[A-Za-z0-9_\-]{10,})\b"      # Resend
)
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\d{10}\b")

_REDACTIONS = (
    (_EMAIL_RE, "[redacted-email]"),
    (_APIKEY_RE, "[redacted-key]"),
    (_PHONE_RE, "[redacted-phone]"),
)


def _redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def redact(text: str) -> str:
    """Apply the log filter's redaction to a string bound for a non-log sink.

    A logging filter only covers records passing through a handler. Anything
    written elsewhere — a resumable script's JSON state file, a report artifact —
    bypasses it entirely, so secret-bearing text headed for disk needs this
    explicitly.
    """
    return _redact(text)


class RedactionFilter(logging.Filter):
    """Redacts PII/secret-looking substrings from the formatted log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        # Structured `extra={"fields": ...}` never passes through `getMessage()`,
        # so it would otherwise reach the sink unredacted — the same blind spot
        # as the v10.40.3 state-file leak, where a filter covered the log line
        # and missed the value written beside it.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            try:
                record.fields = {  # type: ignore[attr-defined]
                    k: (_redact(v) if isinstance(v, str) else v) for k, v in fields.items()
                }
            except Exception:
                pass
        return True


def configure_script_logging(level: int = logging.INFO) -> None:
    """Console logging for standalone scripts, with the app's redaction applied.

    `logging.basicConfig()` attaches no filters, so a script can log a secret the
    running app would have redacted. That is not hypothetical: httpx embeds the
    full request URL — API key and all — in `HTTPStatusError`'s message, so any
    script logging a caught exception verbatim writes the key to its console.

    Plain-text (not JSON) on stderr, since these are read by a human in a
    terminal rather than shipped to an aggregator. `httpx` is pinned to WARNING
    because its INFO line logs every request URL.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    # Replace anything basicConfig() already installed, or the record would also
    # reach an unfiltered handler.
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.setLevel(level)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class JsonFormatter(logging.Formatter):
    """Minimal structured (single-line JSON) formatter — easy to ship to any
    log aggregator (Datadog, CloudWatch, Loki, etc.) without extra deps."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Structured payload from `logger.info(..., extra={"fields": {...}})`.
        # Nested under one key rather than merged at the top level so a field
        # named "level" or "message" can never shadow the record's own.
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict) and fields:
            payload["fields"] = fields
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotent app-wide logging setup. Call once at process startup."""
    root = logging.getLogger()
    if getattr(root, "_wanderplanner_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    root._wanderplanner_configured = True  # type: ignore[attr-defined]

    _configure_sentry()


def _configure_sentry() -> None:
    """Best-effort Sentry init — a no-op unless SENTRY_DSN is set.

    Kept optional/soft-fail (missing SDK or bad DSN must never crash
    startup): this is the "basic observability" half of the logging setup,
    complementing the structured-JSON logs above with error aggregation and
    alerting once a Sentry project is wired up in production.
    """
    if not settings.sentry_dsn:
        logging.getLogger("wanderplanner.logging").info(
            "SENTRY_DSN not set — error tracking/APM disabled (structured JSON logs still active)."
        )
        return

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )
        logging.getLogger("wanderplanner.logging").info(
            "Sentry initialized (environment=%s)", settings.sentry_environment
        )
    except ImportError:
        logging.getLogger("wanderplanner.logging").warning(
            "SENTRY_DSN is set but sentry-sdk is not installed — run: pip install sentry-sdk"
        )
    except Exception:
        logging.getLogger("wanderplanner.logging").exception("Failed to initialize Sentry — continuing without it")
