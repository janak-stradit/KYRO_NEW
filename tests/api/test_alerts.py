"""
tests/app/test_alerts.py — Alert assignment, resolution, escalation, and RBAC.
"""
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.db


def _create_alert_via_sanctions_hit(client, auth_headers, email):
    resp = client.post(
        "/api/v1/customers", json={"full_name": "Risky Corp", "email": email, "customer_type": "CORPORATE"}, headers=auth_headers
    )
    customer = resp.json()
    client.put(f"/api/v1/customers/{customer['id']}", json={"sanctions_flag": True}, headers=auth_headers)

    resp = client.post(
        "/api/v1/accounts",
        json={"customer_id": customer["id"], "account_type": "CHECKING", "balance": 1000},
        headers=auth_headers,
    )
    account = resp.json()

    client.post(
        "/api/v1/transactions",
        json={
            "customer_id": customer["id"],
            "account_id": account["id"],
            "transaction_date": datetime.now(timezone.utc).isoformat(),
            "transaction_type": "TRANSFER",
            "amount": 500,
        },
        headers=auth_headers,
    )

    alerts = client.get("/api/v1/alerts", params={"customer_id": customer["id"]}, headers=auth_headers).json()
    return alerts["items"][0]


def test_assign_alert(client, auth_headers, analyst_user):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "assign.alert@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/assign", json={"assigned_to": str(analyst_user.id)}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ASSIGNED"


def test_analyst_cannot_resolve_alert(client, auth_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "no.resolve@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/resolve", json={"resolution_notes": "Cleared"}, headers=auth_headers)
    assert resp.status_code == 403


def test_compliance_officer_can_resolve_alert(client, auth_headers, compliance_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "compliance.resolve@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/resolve", json={"resolution_notes": "False positive"}, headers=compliance_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RESOLVED"
    assert body["resolution_notes"] == "False positive"


def test_escalate_alert(client, auth_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "escalate.alert@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/escalate", json={"resolution_notes": "Needs MLRO review"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ESCALATED"


def test_get_unknown_alert_404(client, auth_headers):
    resp = client.get("/api/v1/alerts/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404
