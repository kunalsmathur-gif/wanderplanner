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
_APIKEY_RE = re.compile(r"\b(AIza[0-9A-Za-z_\-]{10,}|sk-[A-Za-z0-9]{10,}|gsk_[A-Za-z0-9]{10,})\b")
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


class RedactionFilter(logging.Filter):
    """Redacts PII/secret-looking substrings from the formatted log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = _redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


class JsonFormatter(logging.Formatter):
    """Minimal structured (single-line JSON) formatter — easy to ship to any
    log aggregator (Datadog, CloudWatch, Loki, etc.) without extra deps."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotent app-wide logging setup. Call once at process startup."""
    root = logging.getLogger()
    if getattr(root, "_wanderplan_configured", False):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    root._wanderplan_configured = True  # type: ignore[attr-defined]
