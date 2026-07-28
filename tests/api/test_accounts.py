"""
tests/app/test_accounts.py — Account CRUD, transactions listing, and status updates.
"""
import pytest

pytestmark = pytest.mark.db


def _create_customer(client, auth_headers, email="acct.owner@example.com"):
    resp = client.post(
        "/api/v1/customers",
        json={"full_name": "Acct Owner", "email": email, "customer_type": "INDIVIDUAL"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _create_account(client, auth_headers, customer_id, **overrides):
    payload = {"customer_id": customer_id, "account_type": "CHECKING", "currency": "USD", "balance": 1000, **overrides}
    resp = client.post("/api/v1/accounts", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_account_requires_existing_customer(client, auth_headers):
    resp = client.post(
        "/api/v1/accounts",
        json={"customer_id": "00000000-0000-0000-0000-000000000000", "account_type": "CHECKING"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_create_and_get_account(client, auth_headers):
    customer = _create_customer(client, auth_headers)
    account = _create_account(client, auth_headers, customer["id"])
    assert account["account_status"] == "ACTIVE"

    resp = client.get(f"/api/v1/accounts/{account['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == customer["id"]


def test_list_accounts_filter_by_customer(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="filter.acct@example.com")
    _create_account(client, auth_headers, customer["id"])
    resp = client.get("/api/v1/accounts", params={"customer_id": customer["id"]}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_account_transactions_starts_empty(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="empty.txns@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    resp = client.get(f"/api/v1/accounts/{account['id']}/transactions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_update_account_status(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="status.acct@example.com")
    account = _create_account(client, auth_headers, customer["id"])
    resp = client.put(f"/api/v1/accounts/{account['id']}/status", json={"account_status": "FROZEN"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["account_status"] == "FROZEN"
