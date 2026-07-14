"""
tests/app/test_customers.py — Customer CRUD, risk profile, and KYC review endpoints.
"""
import pytest

pytestmark = pytest.mark.db


def _create_customer(client, auth_headers, **overrides):
    payload = {
        "full_name": "Jane Doe",
        "email": overrides.pop("email", "jane.doe@example.com"),
        "phone": "+1-555-0100",
        "country": "US",
        "residency_country": "US",
        "customer_type": "INDIVIDUAL",
        **overrides,
    }
    resp = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_get_customer(client, auth_headers):
    customer = _create_customer(client, auth_headers)
    assert customer["kyc_status"] == "PENDING"
    assert customer["risk_level"] == "LOW"

    resp = client.get(f"/api/v1/customers/{customer['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "jane.doe@example.com"


def test_get_unknown_customer_404(client, auth_headers):
    resp = client.get("/api/v1/customers/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


def test_update_customer(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="update.me@example.com")
    resp = client.put(
        f"/api/v1/customers/{customer['id']}",
        json={"kyc_status": "VERIFIED", "risk_level": "MEDIUM", "risk_score": 40},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kyc_status"] == "VERIFIED"
    assert body["risk_level"] == "MEDIUM"
    assert body["risk_score"] == 40


def test_list_customers_filter_by_kyc_status(client, auth_headers):
    _create_customer(client, auth_headers, email="filter.me@example.com")
    resp = client.get("/api/v1/customers", params={"kyc_status": "PENDING"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert all(c["kyc_status"] == "PENDING" for c in body["items"])


def test_kyc_review_create_and_list(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="kyc.review@example.com")
    resp = client.post(
        f"/api/v1/customers/{customer['id']}/kyc-reviews",
        json={"review_type": "PERIODIC", "findings": "Initial review"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["review_status"] == "SCHEDULED"

    resp = client.get(f"/api/v1/customers/{customer['id']}/kyc-reviews", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_screening_list_empty_for_new_customer(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="screening.me@example.com")
    resp = client.get(f"/api/v1/customers/{customer['id']}/screening", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_customer_soft_deletes(client, auth_headers):
    customer = _create_customer(client, auth_headers, email="delete.me@example.com")
    resp = client.delete(f"/api/v1/customers/{customer['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/customers/{customer['id']}", headers=auth_headers)
    assert resp.json()["kyc_status"] == "REJECTED"
