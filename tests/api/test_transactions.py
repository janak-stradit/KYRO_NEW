"""
tests/app/test_transactions.py — Transaction ingestion and rules-engine scoring via the API.
"""
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.db


def _create_customer(client, auth_headers, email="txn.owner@example.com", **overrides):
    payload = {"full_name": "Txn Owner", "email": email, "customer_type": "INDIVIDUAL", **overrides}
    resp = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


def _create_account(client, auth_headers, customer_id):
    resp = client.post(
        "/api/v1/accounts",
        json={"customer_id": customer_id, "account_type": "CHECKING", "currency": "USD", "balance": 5000},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _txn_payload(customer_id, account_id, **overrides):
    return {
        "customer_id": customer_id,
        "account_id": account_id,
        "transaction_date": datetime.now(timezone.utc).isoformat(),
        "transaction_type": "TRANSFER",
        "amount": 250.55,
        "currency": "USD",
        "meta_counterparty": "Acme Corp",
        **overrides,
    }


def test_small_transaction_no_rules_triggered(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="small.txn@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    # Fixed weekday (2026-07-13 is a Monday) so R008 (Weekend Activity) can't
    # flakily trigger depending on when the suite runs, and no counterparty
    # so R007 (New Counterparty) — which always fires on a first transaction
    # to a given counterparty — doesn't either.
    payload = _txn_payload(
        customer["id"],
        account["id"],
        transaction_date="2026-07-13T10:00:00+00:00",
        meta_counterparty=None,
    )
    resp = client.post("/api/v1/transactions", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["risk_score"] == 0


def test_transaction_requires_matching_account(client, auth_headers):
    customer_a = _create_customer(client, auth_headers, email="a.owner@example.com")
    customer_b = _create_customer(client, auth_headers, email="b.owner@example.com")
    account_b = _create_account(client, auth_headers, customer_b["id"])
    resp = client.post(
        "/api/v1/transactions", json=_txn_payload(customer_a["id"], account_b["id"]), headers=auth_headers
    )
    assert resp.status_code == 400


def test_large_amount_triggers_r001_and_creates_flags(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="large.txn@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    resp = client.post(
        "/api/v1/transactions",
        json=_txn_payload(customer["id"], account["id"], amount=15000, meta_counterparty="First Time Corp"),
        headers=auth_headers,
    )
    assert resp.status_code == 201
    txn = resp.json()
    assert txn["risk_score"] > 0

    risk = client.get(f"/api/v1/transactions/{txn['id']}/risk", headers=auth_headers).json()
    assert "R001" in risk["triggered_rules"]

    flags = client.get(f"/api/v1/transactions/{txn['id']}/flags", headers=auth_headers).json()
    flag_types = {f["flag_type"] for f in flags}
    assert "R001" in flag_types


def test_sanctioned_customer_triggers_critical_alert(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="sanctioned.txn@example.com")
    resp = client.put(f"/api/v1/customers/{customer['id']}", json={"sanctions_flag": True}, headers=auth_headers)
    assert resp.status_code == 200
    account = _create_account(client, auth_headers, customer["id"])

    resp = client.post("/api/v1/transactions", json=_txn_payload(customer["id"], account["id"]), headers=auth_headers)
    assert resp.status_code == 201
    txn = resp.json()

    risk = client.get(f"/api/v1/transactions/{txn['id']}/risk", headers=auth_headers).json()
    assert "R006" in risk["triggered_rules"]

    alerts = client.get("/api/v1/alerts", params={"customer_id": customer["id"]}, headers=auth_headers).json()
    assert alerts["total"] == 1
    assert alerts["items"][0]["recommended_action"] == "SAR"


def test_batch_ingest(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="batch.txn@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    payload = {
        "transactions": [
            _txn_payload(customer["id"], account["id"], amount=100),
            _txn_payload(customer["id"], account["id"], amount=200),
        ]
    }
    resp = client.post("/api/v1/transactions/batch", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    assert len(resp.json()) == 2
