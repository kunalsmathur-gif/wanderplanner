"""Agentic router — static vs real-time query classifier (issue #35,
docs/rag-strategy.md roadmap P3, §12).

A cheap, zero-cost heuristic (keyword + relative-time-reference detection)
that decides whether a user's chat/wizard query should be routed to the
static vector DB (Qdrant RAG retrieval, already implemented — "best time to
visit Kyoto", "top temples in Kyoto") or would ideally be answered from a
live/real-time source ("is it raining in Kyoto right now", "any strikes in
Paris this week", "flight prices to Tokyo this week").

Deliberately **not** an extra LLM call — the issue's whole point is that this
routing decision must add no cost. Live sources (X/Twitter, live flight
pricing APIs, etc.) are separate paid-API issues and out of scope here: when
a query is classified "real-time" but no live source is wired up (true for
all query types today), this module still reports `source == "web"` so
callers/tests can assert the *classification* is correct, but callers must
treat that as "no live source available yet" and fall back to the existing
static Qdrant path, surfacing a freshness caveat rather than failing or
silently answering as if the information were current.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.keyword_match import has_keyword

# Explicit "right now" markers — the strongest, least ambiguous signal that
# an answer would go stale within hours, not months.
_IMMEDIATE_MARKERS = frozenset({
    "right now", "currently", "at the moment", "as of today", "as of now",
})

# Short, rolling time windows — days out, not "best season" style questions.
_NEAR_TERM_MARKERS = frozenset({
    "today", "tomorrow", "tonight", "this week", "this weekend",
    "next few days", "these days",
})

# Topics that are inherently volatile regardless of the time marker used —
# weather, prices, and disruption/safety events change by the hour/day, so a
# static corpus answer would mislead even without an explicit "now"/"today".
_VOLATILE_TOPIC_MARKERS = frozenset({
    "weather", "raining", "rainfall", "forecast", "temperature right now",
    "strike", "strikes", "protest", "protests", "riot", "riots", "curfew",
    "flight price", "flight prices", "ticket price", "ticket prices",
    "airfare", "fare right now", "current price", "live price",
    "open now", "closed now", "is it open", "still open",
    "breaking news", "travel advisory update", "border closed", "border closure",
})


@dataclass(frozen=True)
class QueryRoute:
    """Result of classifying one user query."""

    # "qdrant" — static vector DB retrieval (the only implemented path).
    # "web" — this query is genuinely time-sensitive; there is no live
    #   source wired up yet, so callers must fall back to "qdrant" for the
    #   actual retrieval while treating `note` as a freshness caveat to
    #   surface to the user, per the issue's explicit "fall back gracefully"
    #   requirement.
    source: str
    matched_keywords: tuple[str, ...]
    note: str | None


_STATIC_NOTE = None
_REALTIME_NOTE = (
    "This looks like it needs up-to-the-minute information (weather, prices, "
    "or a live disruption) rather than general travel knowledge — mention "
    "that the details can change and suggest the traveller double-check a "
    "live/official source closer to the trip, rather than presenting a "
    "guess as current fact."
)


def route_query(text: str | None) -> QueryRoute:
    """Classify a single user query as static ("qdrant") or time-sensitive
    ("web"). Pure heuristic, no LLM call, no I/O — safe to call on every
    turn at negligible cost."""
    if not text:
        return QueryRoute(source="qdrant", matched_keywords=(), note=_STATIC_NOTE)

    matched: list[str] = []
    for bucket in (_IMMEDIATE_MARKERS, _NEAR_TERM_MARKERS, _VOLATILE_TOPIC_MARKERS):
        for kw in bucket:
            if has_keyword(text, [kw]):
                matched.append(kw)

    if matched:
        return QueryRoute(source="web", matched_keywords=tuple(sorted(matched)), note=_REALTIME_NOTE)
    return QueryRoute(source="qdrant", matched_keywords=(), note=_STATIC_NOTE)
