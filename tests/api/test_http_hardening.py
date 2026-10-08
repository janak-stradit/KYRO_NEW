"""
tests/api/test_http_hardening.py — CORS allow-list and rate limiting (README quick wins).
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.rate_limit import limiter


def test_cors_rejects_unlisted_origin(client):
    resp = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_cors_allows_listed_origin(client):
    resp = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_wildcard_is_ignored():
    settings = Settings(cors_allowed_origins="*, https://kyro.example ,")
    assert settings.cors_origins == ["https://kyro.example"]


@pytest.fixture
def rate_limited():
    limiter.reset()
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


def test_login_is_rate_limited(client, rate_limited):
    statuses = [
        client.post("/api/v1/auth/login", data={"username": "nobody", "password": "wrong"}).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_health_is_exempt_from_rate_limit(client, rate_limited):
    for _ in range(15):
        assert client.get("/api/v1/health").status_code == 200
