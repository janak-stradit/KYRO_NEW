"""
tests/api/test_kyrochat.py — Tests for the Kyro Chat, autonomous agent controls, and streaming simulation endpoints.
"""
import pytest

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _signed_in(client, auth_headers):
    client.headers.update(auth_headers)


def test_chat_agent_and_streaming_need_a_signed_in_user(client):
    client.headers.pop("Authorization")
    assert client.get("/api/v1/chat/welcome").status_code == 401
    assert client.post("/api/v1/chat/message", json={"messages": [{"role": "user", "content": "backlog"}]}).status_code == 401
    assert client.get("/api/v1/agent/autonomous/cases/processing").status_code == 401
    assert client.post("/api/v1/streaming/start", json={}).status_code == 401
    assert client.post("/api/v1/tts/speak", json={"text": "hello"}).status_code == 401

def test_chat_welcome_endpoint(client):
    resp = client.get("/api/v1/chat/welcome")
    assert resp.status_code == 200
    body = resp.json()
    assert "message" in body
    assert body["is_welcome"] is True
    assert len(body["options"]) > 0

def test_chat_message_endpoint(client):
    # Test backlog query
    resp = client.post("/api/v1/chat/message", json={
        "messages": [{"role": "user", "content": "What is the status of the backlog?"}]
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "backlog" in body["content"] or "alerts" in body["content"]
    assert len(body["suggestions"]) > 0

    # Test ML model performance query
    resp = client.post("/api/v1/chat/message", json={
        "messages": [{"role": "user", "content": "How is the ML model performing?"}]
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "XGBoost" in body["content"] or "Classifier" in body["content"]

def test_agent_status_endpoint(client):
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "runStats" in body

def test_agent_state_transitions(client):
    # Initial status should be STOPPED
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "STOPPED"

    # Start agent
    resp = client.post("/api/v1/agent/autonomous/start", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Status should be RUNNING
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "RUNNING"

    # Pause agent
    resp = client.post("/api/v1/agent/autonomous/pause", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Status should be PAUSED
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "PAUSED"

    # Resume agent
    resp = client.post("/api/v1/agent/autonomous/resume", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Status should be RUNNING
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "RUNNING"

    # Handoff agent
    resp = client.post("/api/v1/agent/autonomous/handoff", json={"reason": "requires compliance signature"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Status should be PAUSED
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "PAUSED"
    assert resp.json()["interventionNeeded"] is True

    # Stop agent
    resp = client.post("/api/v1/agent/autonomous/stop", json={})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Status should be STOPPED
    resp = client.get("/api/v1/agent/autonomous/status")
    assert resp.json()["status"] == "STOPPED"

def test_streaming_endpoints(client):
    # Get initial status
    resp = client.get("/api/v1/streaming/status")
    assert resp.status_code == 200
    
    # Start streaming
    resp = client.post("/api/v1/streaming/start", json={"event_types": ["transaction"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"
    
    # Get running status
    resp = client.get("/api/v1/streaming/status")
    assert resp.json()["is_running"] is True
    
    # Stop streaming
    resp = client.post("/api/v1/streaming/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"
    
    # Get stopped status
    resp = client.get("/api/v1/streaming/status")
    assert resp.json()["is_running"] is False
