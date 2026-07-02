"""Shared helpers for turning internal exceptions into safe client responses.

Raw exception text (provider errors, stack traces, file paths) must never be
sent to clients — it leaks infra/provider details useful for recon. Log the
full detail server-side and return a generic, sanitized message instead.
See docs/scaling-tech-challenges.md, Security Vulnerabilities #5.
"""
from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("wanderplan.errors")

GENERIC_MESSAGE = "Something went wrong while processing your request. Please try again."


def sanitize_error(exc: Exception, *, context: str = "") -> str:
    """Log the full exception server-side and return a safe, generic message.

    Returns a short reference id in the message so a user can report it
    without any internal detail being exposed.
    """
    error_id = uuid.uuid4().hex[:8]
    logger.exception("Unhandled error [%s]%s: %s", error_id, f" in {context}" if context else "", exc)
    return f"{GENERIC_MESSAGE} (ref: {error_id})"
