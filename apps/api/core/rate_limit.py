"""Shared rate limiter for LLM-backed and abuse-prone endpoints.

In-memory storage is a stopgap: fine for a single instance, but must move to a
Redis backend (`storage_uri="redis://..."`) before running more than one API
process, since counters would otherwise be inconsistent per-instance.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Endpoints that trigger one or more LLM calls: keep this tight, cost is the
# primary risk (see docs/scaling-tech-challenges.md, finding #6).
LLM_RATE_LIMIT = "10/minute"

# Cheaper/read-mostly endpoints (share lookups, geocoding, etc.) that we still
# want to blunt brute-force/enumeration attempts against.
DEFAULT_RATE_LIMIT = "30/minute"
