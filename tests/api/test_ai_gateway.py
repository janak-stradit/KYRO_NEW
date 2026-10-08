"""
tests/api/test_ai_gateway.py — Compliance AI foundation (Phase 11.0): redaction,
prompt registry, gateway kill switch / mock / provider, and admin endpoints.
No test makes a real network call.
"""
from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.ai import AIDisabledError, AIGateway, AIProviderError, PromptError, get_prompt
from app.ai.prompts import load_prompts
from app.ai.redaction import Redactor
from app.config import get_settings
from app.models.ai_interaction import AIInteraction

pytestmark = pytest.mark.db


@pytest.fixture
def ai_settings(monkeypatch):
    """AI enabled in mock mode; individual tests flip what they need."""
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", True)
    monkeypatch.setattr(settings, "kyro_llm_base_url", "")
    monkeypatch.setattr(settings, "kyro_llm_api_key", SecretStr(""))
    return settings


# ── Redaction ────────────────────────────────────────────────────────────

def test_redaction_replaces_known_values_and_patterns_and_restores():
    r = Redactor(known={"John James": "PERSON", "CUST-001": "CUSTOMER_ID"})
    original = (
        "John James (CUST-001) emailed john.james@example.com from +44 20 7946 0958 "
        "about account 12345678901 on 2026-09-14. john james confirmed."
    )
    redacted = r.redact(original)

    for secret in ["John James", "CUST-001", "john.james@example.com", "7946", "12345678901", "2026-09-14"]:
        assert secret not in redacted
    assert "[PERSON_1]" in redacted and "[CUSTOMER_ID_1]" in redacted and "[EMAIL_1]" in redacted
    assert r.restore(redacted) == original


def test_redaction_reuses_placeholder_for_repeated_value():
    r = Redactor(known={"Susan Powell": "PERSON"})
    redacted = r.redact("Susan Powell and Susan Powell")
    assert redacted == "[PERSON_1] and [PERSON_1]"
    assert r.count == 1


# ── Prompt registry ──────────────────────────────────────────────────────

def test_prompt_registry_loads_versioned_prompts():
    prompts = load_prompts()
    prompt = get_prompt("system.connectivity_check")
    assert prompt.id in prompts
    assert prompt.version >= 1 and prompt.response_format == "json"
    assert prompt.variables() == {"nonce"}


def test_prompt_render_requires_all_variables():
    with pytest.raises(PromptError, match="nonce"):
        get_prompt("system.connectivity_check").render({})


# ── Gateway ──────────────────────────────────────────────────────────────

def test_gateway_disabled_raises_and_logs(db_session, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_ai_enabled", False)
    with pytest.raises(AIDisabledError):
        AIGateway(db_session).run("system.connectivity_check", {"nonce": "n1"})
    row = db_session.query(AIInteraction).order_by(AIInteraction.created_at.desc()).first()
    assert row.status == "DISABLED"


def test_gateway_mock_round_trip_redacts_and_logs(db_session, ai_settings):
    # The "nonce" carries personal data to prove it never reaches the provider
    result = AIGateway(db_session).run(
        "system.connectivity_check",
        {"nonce": "john.james@example.com"},
        sensitive={"John James": "PERSON"},
        entity_type="ALERT",
    )
    assert result.provider == "mock"
    assert result.data["echo"] == "john.james@example.com"  # restored for the caller
    assert result.redaction_count >= 1

    row = db_session.get(AIInteraction, result.interaction_id)
    assert row.status == "SUCCESS"
    assert row.prompt_id == "system.connectivity_check" and row.prompt_version == 1
    assert "john.james@example.com" not in row.input_redacted
    assert "john.james@example.com" not in (row.output_text or "")
    assert row.entity_type == "ALERT"


def test_openai_compatible_provider_parses_reply(db_session, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_llm_mock", False)
    monkeypatch.setattr(ai_settings, "kyro_llm_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(ai_settings, "kyro_llm_api_key", SecretStr("sk-testkey12345678"))
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, body=json)
        nonce = json["messages"][-1]["content"].split('"echo": "')[1].split('"')[0]
        return httpx.Response(200, json={
            "model": "test-model",
            "choices": [{"message": {"content": f'```json\n{{"status": "ok", "echo": "{nonce}"}}\n```'}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 9},
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    result = AIGateway(db_session).run("system.connectivity_check", {"nonce": "abc123"})

    assert captured["url"] == "https://llm.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-testkey12345678"
    assert captured["body"]["model"] == ai_settings.kyro_llm_model
    assert result.data == {"status": "ok", "echo": "abc123"}
    row = db_session.get(AIInteraction, result.interaction_id)
    assert (row.prompt_tokens, row.completion_tokens, row.model) == (42, 9, "test-model")


def test_provider_errors_are_logged_without_secrets(db_session, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_llm_mock", False)
    monkeypatch.setattr(ai_settings, "kyro_llm_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(ai_settings, "kyro_llm_api_key", SecretStr("sk-testkey12345678"))
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, text="invalid key sk-testkey12345678"))

    with pytest.raises(AIProviderError) as exc_info:
        AIGateway(db_session).run("system.connectivity_check", {"nonce": "x"})
    assert "sk-testkey12345678" not in str(exc_info.value)
    row = db_session.query(AIInteraction).order_by(AIInteraction.created_at.desc()).first()
    assert row.status == "ERROR" and "sk-testkey12345678" not in row.error


def test_real_provider_requires_endpoint_and_key(db_session, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_llm_mock", False)
    with pytest.raises(AIProviderError, match="KYRO_LLM_BASE_URL"):
        AIGateway(db_session).run("system.connectivity_check", {"nonce": "x"})


# ── Endpoints ────────────────────────────────────────────────────────────

def test_status_endpoint_never_returns_the_key(client, admin_headers, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_llm_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(ai_settings, "kyro_llm_api_key", SecretStr("sk-testkey12345678"))
    resp = client.get("/api/v1/ai/status", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_configured"] is True and body["endpoint_host"] == "llm.example.test"
    assert "sk-testkey12345678" not in resp.text


def test_status_endpoint_requires_admin_or_compliance(client, auth_headers, compliance_headers):
    assert client.get("/api/v1/ai/status", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/ai/status", headers=compliance_headers).status_code == 200


def test_check_endpoint_mock_mode(client, admin_headers, ai_settings):
    resp = client.post("/api/v1/ai/check", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["provider"] == "mock"


def test_check_endpoint_when_disabled(client, admin_headers, ai_settings, monkeypatch):
    monkeypatch.setattr(ai_settings, "kyro_ai_enabled", False)
    assert client.post("/api/v1/ai/check", headers=admin_headers).status_code == 409


def test_search_endpoint_returns_cited_chunks_or_nothing(client, auth_headers, db_session):
    from app.ai.retrieval import index_text

    index_text(
        db_session, source_type="POLICY", source_ref="Policy ZZ-99", version="v1", citation="Section 4",
        title="Zebra crossing retention schedule", text="Zebra crossing records are retained for seven years.",
    )
    db_session.commit()

    resp = client.get("/api/v1/ai/search", params={"q": "zebra crossing retention"}, headers=auth_headers)
    assert resp.status_code == 200
    top = resp.json()["results"][0]
    assert (top["source_ref"], top["version"], top["citation"]) == ("Policy ZZ-99", "v1", "Section 4")

    resp = client.get("/api/v1/ai/search", params={"q": "xylophone tuning frequency"}, headers=auth_headers)
    assert resp.json()["results"] == []
    assert client.get("/api/v1/ai/search", params={"q": "zebra"}).status_code == 401
