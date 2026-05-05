"""Redis cache client — backed by Google Cloud Memorystore for Redis.

Falls back to a no-op in-memory dict when Redis is not configured
(REDIS_URL env var not set) so local development works without Redis.

Usage:
    from backend.app.core.cache import get_cache, set_cache, cache_key

    key = cache_key("ad_gen", prompt_hash, platform, brand_id)
    result = await get_cache(key)
    if result is None:
        result = await expensive_operation()
        await set_cache(key, result, ttl=7200)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

logger = logging.getLogger("vantage.cache")

_REDIS_URL = os.environ.get("REDIS_URL", "")
_redis_client = None
_memory_store: dict[str, str] = {}  # fallback for local dev


def _get_redis():
    global _redis_client
    if _redis_client is None and _REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
        except Exception as exc:
            logger.warning("Redis connection failed: %s — using in-memory fallback.", exc)
    return _redis_client


async def get_cache(key: str) -> Any | None:
    """Return cached value or None if not found / expired."""
    r = _get_redis()
    try:
        if r:
            raw = await r.get(key)
        else:
            raw = _memory_store.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.debug("Cache get failed for key '%s': %s", key, exc)
        return None


async def set_cache(key: str, value: Any, ttl: int = 3600) -> None:
    """Store a value in cache with TTL in seconds."""
    serialized = json.dumps(value)
    r = _get_redis()
    try:
        if r:
            await r.setex(key, ttl, serialized)
        else:
            _memory_store[key] = serialized
    except Exception as exc:
        logger.debug("Cache set failed for key '%s': %s", key, exc)


async def invalidate(key: str) -> None:
    """Delete a cache entry."""
    r = _get_redis()
    try:
        if r:
            await r.delete(key)
        else:
            _memory_store.pop(key, None)
    except Exception:
        pass


def cache_key(*parts: str) -> str:
    """Build a stable cache key from parts."""
    raw = "|".join(str(p) for p in parts)
    return "vantage:" + hashlib.md5(raw.encode()).hexdigest()


# TTL constants
TTL_AD_GEN = 7200       # 2 hours — same brief rarely changes within a session
TTL_RAG_QUERY = 1800    # 30 minutes — training data can be updated anytime
TTL_BQ_ANALYTICS = 86400  # 24 hours — historical aggregates are stable
