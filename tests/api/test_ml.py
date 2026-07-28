"""
tests/api/test_ml.py — ML scoring, training RBAC, model registry, and
performance endpoints.

Scoring tests need trained models on disk (app.ml.registry.ModelRegistry),
built from real committed transaction data — not the per-test SAVEPOINT data,
since a trained model has to generalize across more than a couple of rows.
`_ensure_models_trained` trains a small model once per session (reusing
whatever's already in the registry from a prior run/seed) rather than
depending on an external seeding step having been run first.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database import SessionLocal
from app.ml.registry.model_registry import ModelRegistry
from app.ml.training.pipeline import MODEL_NAMES, run_training_pipeline

pytestmark = pytest.mark.db


@pytest.fixture(scope="session", autouse=True)
def _ensure_models_trained():
    registry = ModelRegistry()
    if all(registry.list_versions(name) for name in MODEL_NAMES):
        return
    db = SessionLocal()
    try:
        from app.models.transaction import Transaction

        count = db.query(Transaction).count()
    finally:
        db.close()
    if count < 50:
        pytest.skip("No trained models and not enough committed transaction data to train — run scripts/seed_app_data.py first")
    run_training_pipeline(limit=min(count, 1000))


def _create_customer(client, auth_headers, email):
    resp = client.post(
        "/api/v1/customers", json={"full_name": "ML Test", "email": email, "customer_type": "INDIVIDUAL"}, headers=auth_headers
    )
    assert resp.status_code == 201
    return resp.json()


def _create_account(client, auth_headers, customer_id):
    resp = client.post(
        "/api/v1/accounts", json={"customer_id": customer_id, "account_type": "CHECKING", "balance": 5000}, headers=auth_headers
    )
    assert resp.status_code == 201
    return resp.json()


def _create_transaction(client, auth_headers, customer_id, account_id, **overrides):
    payload = {
        "customer_id": customer_id,
        "account_id": account_id,
        "transaction_date": datetime.now(timezone.utc).isoformat(),
        "transaction_type": "TRANSFER",
        "amount": 500,
        **overrides,
    }
    resp = client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


def test_score_transaction_returns_explanation(client, auth_headers):
    customer = _create_customer(client, auth_headers, "ml.score.txn@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    txn = _create_transaction(client, auth_headers, customer["id"], account["id"], amount=15000)

    resp = client.post("/api/v1/ml/score-transaction", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 0 <= body["risk_score"] <= 100
    assert isinstance(body["anomaly_flag"], bool)
    assert body["ml_explanation"]["top_features"]
    assert body["recommended_action"] in ("NONE", "BATCH_REVIEW", "IMMEDIATE_REVIEW")


def test_score_transaction_unknown_id_404(client, auth_headers):
    resp = client.post(
        "/api/v1/ml/score-transaction",
        json={"transaction_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_score_transaction_high_risk_creates_alert(client, auth_headers):
    customer = _create_customer(client, auth_headers, "ml.highrisk@example.com")
    client.put(f"/api/v1/customers/{customer['id']}", json={"sanctions_flag": True}, headers=auth_headers)
    account = _create_account(client, auth_headers, customer["id"])
    txn = _create_transaction(
        client, auth_headers, customer["id"], account["id"], amount=90000, meta_country="IR", meta_destination_country="IR"
    )

    resp = client.post("/api/v1/ml/score-transaction", json={"transaction_id": txn["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_score"] > 30
    assert body["alert_created"] is True
    assert body["alert_id"] is not None


def test_score_customer(client, auth_headers):
    customer = _create_customer(client, auth_headers, "ml.score.cust@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    _create_transaction(client, auth_headers, customer["id"], account["id"])

    resp = client.post(f"/api/v1/ml/score-customer/{customer['id']}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == customer["id"]
    assert 0 <= body["overall_risk"] <= 100


def test_score_customer_no_recent_activity(client, auth_headers):
    customer = _create_customer(client, auth_headers, "ml.no.activity@example.com")
    resp = client.post(f"/api/v1/ml/score-customer/{customer['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["trend_summary"] == "No recent transaction activity"


def test_list_models(client, auth_headers):
    resp = client.get("/api/v1/ml/models", headers=auth_headers)
    assert resp.status_code == 200
    names = {m["name"] for m in resp.json()}
    assert names == set(MODEL_NAMES)


def test_train_requires_admin(client, auth_headers):
    resp = client.post("/api/v1/ml/train", json={"limit": 200}, headers=auth_headers)
    assert resp.status_code == 403


def test_train_as_admin_succeeds(client, admin_headers):
    resp = client.post("/api/v1/ml/train", json={"as_candidate": True, "limit": 100}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert set(body["versions"]) == set(MODEL_NAMES)


def test_performance_endpoint_shape(client, auth_headers):
    resp = client.get("/api/v1/ml/performance", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "precision" in body
    assert "false_positive_rate" in body
    assert body["window_days"] == 30
