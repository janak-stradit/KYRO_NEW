"""
tests/app/test_auth.py — Login, refresh, and current-user endpoints.
"""
import pytest

pytestmark = pytest.mark.db


def test_login_success(client, analyst_user):
    resp = client.post("/api/v1/auth/login", data={"username": "analyst1", "password": "Str0ngPass!123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password(client, analyst_user):
    resp = client.post("/api/v1/auth/login", data={"username": "analyst1", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post("/api/v1/auth/login", data={"username": "ghost", "password": "whatever"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, auth_headers, analyst_user):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "analyst1"
    assert resp.json()["role"] == "ANALYST"


def test_me_accepts_reserved_tld_email(client, db_session):
    # The demo users seeded in app/main.py use *.local addresses.
    from app.models.user import User
    from app.utils.security import hash_password

    db_session.add(User(
        username="localuser",
        email="localuser@kyro.local",
        hashed_password=hash_password("Str0ngPass!123"),
        role="ANALYST",
    ))
    db_session.commit()
    token = client.post(
        "/api/v1/auth/login", data={"username": "localuser", "password": "Str0ngPass!123"}
    ).json()["access_token"]

    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "localuser@kyro.local"


def test_refresh_issues_new_tokens(client, analyst_user):
    login = client.post("/api/v1/auth/login", data={"username": "analyst1", "password": "Str0ngPass!123"})
    refresh_token = login.json()["refresh_token"]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token(client, auth_headers):
    access_token = auth_headers["Authorization"].split(" ")[1]
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
