"""
tests/app/test_alerts.py — Alert assignment, resolution, escalation, and RBAC.
"""
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.db

_FP_RESOLUTION = {
    "outcome": "FALSE_POSITIVE",
    "reasons": ["SCREENING_NAME_MISMATCH"],
    "resolution_notes": "Name matched a different legal entity",
}


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
    resp = client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_FP_RESOLUTION, headers=auth_headers)
    assert resp.status_code == 403


def test_compliance_officer_can_resolve_alert(client, auth_headers, compliance_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "compliance.resolve@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RESOLVED"
    assert body["resolution_notes"] == "Name matched a different legal entity"
    assert body["resolution_outcome"] == "FALSE_POSITIVE"
    assert body["resolution_reasons"] == ["SCREENING_NAME_MISMATCH"]
    assert body["is_false_positive"] is True
    assert body["resolved_at"] and body["resolved_by"]


def test_resolve_true_positive_outcomes_are_not_false_positives(client, auth_headers, compliance_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "sar.resolve@example.com")
    resp = client.put(
        f"/api/v1/alerts/{alert['id']}/resolve",
        json={
            "outcome": "SAR_FILED",
            "reasons": ["SANCTIONS_EXPOSURE", "SANCTIONS_EXPOSURE"],
            "resolution_notes": "Confirmed exposure",
            "sar_reference": "SAR-2026-0001",
        },
        headers=compliance_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_false_positive"] is False
    assert body["resolution_reasons"] == ["SANCTIONS_EXPOSURE"]  # de-duplicated
    assert body["sar_reference"] == "SAR-2026-0001"


@pytest.mark.parametrize(
    "payload",
    [
        {"resolution_notes": "Cleared"},  # outcome and reasons are required
        {"outcome": "FALSE_POSITIVE", "reasons": [], "resolution_notes": "Cleared"},
        {"outcome": "FALSE_POSITIVE", "reasons": ["RULE_TOO_BROAD"], "resolution_notes": "   "},
        {"outcome": "FALSE_POSITIVE", "reasons": ["STRUCTURING_SUSPECTED"], "resolution_notes": "Cleared"},
        {"outcome": "FALSE_POSITIVE", "reasons": ["NOT_A_CODE"], "resolution_notes": "Cleared"},
        {"outcome": "ESCALATED", "reasons": ["OTHER"], "resolution_notes": "Use /escalate"},
    ],
)
def test_resolve_rejects_incomplete_or_inconsistent_disposition(client, auth_headers, compliance_headers, payload):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "bad.resolve@example.com")
    resp = client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=payload, headers=compliance_headers)
    assert resp.status_code == 422
    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=auth_headers).json()["status"] != "RESOLVED"


def test_resolved_alert_cannot_be_resolved_or_escalated_again(client, auth_headers, compliance_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "twice.resolve@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    assert client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=compliance_headers).status_code == 200
    assert client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=compliance_headers).status_code == 409
    assert client.put(f"{url}/escalate", json={}, headers=auth_headers).status_code == 409


def test_resolution_options_lists_outcomes_with_their_reasons(client, auth_headers):
    resp = client.get("/api/v1/alerts/resolution-options", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    outcomes = {o["code"]: o["reasons"] for o in body["outcomes"]}
    assert set(outcomes) == {"SAR_FILED", "ESCALATED", "TRUE_POSITIVE_NO_SAR", "FALSE_POSITIVE"}
    assert "RULE_TOO_BROAD" in outcomes["FALSE_POSITIVE"] and "RULE_TOO_BROAD" not in outcomes["SAR_FILED"]
    assert {r for reasons in outcomes.values() for r in reasons} == {r["code"] for r in body["reasons"]}


def test_escalate_alert(client, auth_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "escalate.alert@example.com")
    resp = client.put(
        f"/api/v1/alerts/{alert['id']}/escalate",
        json={"resolution_notes": "Needs MLRO review", "reasons": ["SANCTIONS_EXPOSURE"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ESCALATED"
    assert body["resolution_outcome"] == "ESCALATED" and body["resolution_reasons"] == ["SANCTIONS_EXPOSURE"]
    assert body["is_false_positive"] is None and body["resolved_at"] is None


def test_get_unknown_alert_404(client, auth_headers):
    resp = client.get("/api/v1/alerts/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


def test_disposition_baseline_reports_fp_rate_per_rule(client, auth_headers, compliance_headers, db_session):
    from app.models.alert import Alert
    from app.models.customer import Customer

    before = client.get("/api/v1/alerts/disposition-baseline", headers=compliance_headers).json()

    def row(body, section, key, name):
        return next((r for r in body[section] if r[key] == name), {"alerts": 0, "resolved": 0, "false_positives": 0})

    customer = Customer(full_name="Baseline Ltd", email="baseline@example.com", customer_type="CORPORATE")
    db_session.add(customer)
    db_session.flush()
    alerts = [
        Alert(customer_id=customer.id, risk_score=80, triggered_rules={"rules": ["RX91", "RX92"]}),
        Alert(customer_id=customer.id, risk_score=80, triggered_rules={"rules": ["RX91"]}),
        Alert(customer_id=customer.id, risk_score=80, triggered_rules={"rules": ["RX91"]}),
    ]
    db_session.add_all(alerts)
    db_session.commit()

    client.put(f"/api/v1/alerts/{alerts[0].id}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)
    client.put(
        f"/api/v1/alerts/{alerts[1].id}/resolve",
        json={"outcome": "SAR_FILED", "reasons": ["STRUCTURING_SUSPECTED"], "resolution_notes": "Filed"},
        headers=compliance_headers,
    )

    resp = client.get("/api/v1/alerts/disposition-baseline", headers=compliance_headers)
    assert resp.status_code == 200
    body = resp.json()

    rx91 = row(body, "by_rule", "rule", "RX91")
    assert (rx91["alerts"], rx91["resolved"], rx91["false_positives"], rx91["sar_filed"]) == (3, 2, 1, 1)
    assert rx91["false_positive_rate"] == 0.5 and rx91["median_hours_to_disposition"] is not None
    assert rx91["reasons"] == {"SCREENING_NAME_MISMATCH": 1, "STRUCTURING_SUSPECTED": 1}

    rx92 = row(body, "by_rule", "rule", "RX92")
    assert (rx92["alerts"], rx92["false_positive_rate"]) == (1, 1.0)
    combo = row(body, "by_rule_combination", "rules", "RX91+RX92")
    assert (combo["alerts"], combo["false_positives"]) == (1, 1)
    assert body["overall"]["alerts"] == before["overall"]["alerts"] + 3
    assert body["overall"]["false_positives"] == before["overall"]["false_positives"] + 1

    assert client.get("/api/v1/alerts/disposition-baseline", headers=auth_headers).status_code == 403
