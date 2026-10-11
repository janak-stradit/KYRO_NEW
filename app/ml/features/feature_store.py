"""
ml/features/feature_store.py — Redis-backed cache for expensive/shared feature
inputs (currently: the global amount-percentile breakpoints). Uses Redis DB
index 1 so it doesn't collide with Celery's broker/result store on DB 0.

The cache is an optimisation, not a dependency: if Redis cannot be reached,
values are kept in this process instead, so scoring keeps working (each
process then recomputes the value once per TTL).
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

import redis

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("kyro.ml.feature_store")

_REDIS_RETRY_SECONDS = 60
_local: dict[str, tuple[float, str]] = {}  # key -> (expires at, JSON)
_redis_down_until = 0.0


@lru_cache(maxsize=1)
def get_feature_store_redis() -> redis.Redis:
    base = settings.redis_url.rsplit("/", 1)[0]
    # Short timeouts: a missing cache must not stall a scoring request
    return redis.Redis.from_url(f"{base}/1", decode_responses=True, socket_connect_timeout=1, socket_timeout=1)


def _redis_available() -> bool:
    return time.monotonic() >= _redis_down_until


def _mark_redis_down(exc: Exception) -> None:
    global _redis_down_until
    if _redis_available():
        logger.warning("Feature-store Redis unavailable (%s); caching in process for now", type(exc).__name__)
    _redis_down_until = time.monotonic() + _REDIS_RETRY_SECONDS


def cache_json(key: str, value: dict | list, ttl_seconds: int = 3600) -> None:
    payload = json.dumps(value)
    _local[key] = (time.monotonic() + ttl_seconds, payload)
    if _redis_available():
        try:
            get_feature_store_redis().set(key, payload, ex=ttl_seconds)
        except redis.RedisError as exc:
            _mark_redis_down(exc)


def get_cached_json(key: str) -> dict | list | None:
    if _redis_available():
        try:
            raw = get_feature_store_redis().get(key)
            return json.loads(raw) if raw is not None else None
        except redis.RedisError as exc:
            _mark_redis_down(exc)
    entry = _local.get(key)
    if entry is None or entry[0] < time.monotonic():
        _local.pop(key, None)
        return None
    return json.loads(entry[1])
