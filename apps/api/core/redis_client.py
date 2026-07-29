"""Redis-backed cache with an in-process dict fallback for local dev.

This replaces the previously-separate plain-`dict` caches in `routers/share.py`
and `routers/travel_tips.py` — both were correctness bugs, not just scaling
ones (docs/scaling-tech-challenges.md: "In-memory share store / caches become
a shared bottleneck & memory leak risk" / "Data is also lost on every
restart/deploy"). Deployed on Railway 2026-07-29 (the "Redis" template,
available on all plans including Hobby/free tier).

Local dev deliberately does **not** require Redis to be running: if
`REDIS_URL` isn't set, `get_cache()` returns an in-process dict-backed
fallback with the same get/set/delete/flush interface (TTLs enforced on read,
same as before this change) — mirrors `core/qdrant.py`'s `:memory:` fallback
so `npm run dev`/`uvicorn` locally never requires standing up extra infra.
"""
from __future__ import annotations

import logging
import time
from typing import Protocol

from core.config import settings

logger = logging.getLogger(__name__)


class Cache(Protocol):
    async def get_json(self, key: str) -> object | None: ...
    async def set_json(self, key: str, value: object, ttl_seconds: int) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def flush(self) -> None: ...
    async def memory_usage_bytes(self) -> int | None: ...
    async def key_count(self) -> int | None: ...


class _InMemoryCache:
    """Local-dev fallback — same shape as before this change (plain dict per
    router) but centralized and now TTL-enforced, since neither original
    in-memory cache actually expired entries (the travel-tips docstring
    claimed "1h cache" but the code never checked an expiry)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, object]] = {}  # key -> (expires_at, value)

    async def get_json(self, key: str) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def flush(self) -> None:
        self._store.clear()

    async def memory_usage_bytes(self) -> int | None:
        # Not meaningful to estimate for the local dict fallback — headroom
        # monitoring is a production (real Redis) concern.
        return None

    async def key_count(self) -> int | None:
        return len(self._store)


class _RedisCache:
    def __init__(self, client) -> None:
        self._client = client

    async def get_json(self, key: str) -> object | None:
        import json
        raw = await self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: object, ttl_seconds: int) -> None:
        import json
        await self._client.set(key, json.dumps(value), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def flush(self) -> None:
        await self._client.flushdb()

    async def memory_usage_bytes(self) -> int | None:
        info = await self._client.info("memory")
        used = info.get("used_memory")
        return int(used) if used is not None else None

    async def key_count(self) -> int | None:
        return await self._client.dbsize()


_cache: Cache | None = None


def get_cache() -> Cache:
    """Returns the process-wide cache singleton — a real Redis client if
    `REDIS_URL` is configured, otherwise the in-process dict fallback."""
    global _cache
    if _cache is None:
        if settings.redis_url:
            import redis.asyncio as redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            _cache = _RedisCache(client)
            logger.info("Cache backend: Redis (%s)", settings.redis_url.split("@")[-1])
        else:
            _cache = _InMemoryCache()
            logger.info("Cache backend: in-process dict (no REDIS_URL set — local dev fallback)")
    return _cache
