"""
ml/features/feature_store.py — Redis-backed cache for expensive/shared feature
inputs (currently: the global amount-percentile breakpoints). Uses Redis DB
index 1 so it doesn't collide with Celery's broker/result store on DB 0.
"""
from __future__ import annotations

import json
from functools import lru_cache

import redis

from app.config import get_settings

settings = get_settings()


@lru_cache(maxsize=1)
def get_feature_store_redis() -> redis.Redis:
    base = settings.redis_url.rsplit("/", 1)[0]
    return redis.Redis.from_url(f"{base}/1", decode_responses=True)


def cache_json(key: str, value: dict | list, ttl_seconds: int = 3600) -> None:
    get_feature_store_redis().set(key, json.dumps(value), ex=ttl_seconds)


def get_cached_json(key: str) -> dict | list | None:
    raw = get_feature_store_redis().get(key)
    return json.loads(raw) if raw is not None else None
