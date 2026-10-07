"""
rate_limit.py — Shared slowapi limiter (stopgap until a WAF sits in front of the API).

Clients are keyed by IP. Behind nginx this relies on uvicorn's
--proxy-headers so request.client.host is the real client, not the proxy.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_settings.rate_limit_storage_uri or "memory://",
    enabled=_settings.rate_limit_enabled,
    headers_enabled=False,
)
