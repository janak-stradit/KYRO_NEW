"""
tests/api/test_customer_risk.py — Rule-based customer risk rating: factors,
levels, automatic updates when alerts open and close, and the endpoints.
"""
from __future__ import annotations

import pytest

from app.models.alert import Alert
from app.models.audit import AuditLog
from app.models.customer import Customer, CustomerRiskProfile
from app.services import customer_risk_service

pytestmark = pytest.mark.db


def _customer(db_session, name, **flags) -> Customer:
    customer = Customer(
        full_name=name, email=f"{name.lower().replace(' ', '.')}@example.com", customer_type="INDIVIDUAL", **flags
    )
    db_session.add(customer)
    db_session.commit()
    return customer


def _factors(db_session, customer) -> set[str]:
    return {p.risk_factor for p in db_session.query(CustomerRiskProfile).filter_by(customer_id=customer.id)}


def test_customer_with_no_risk_factors_is_low(db_session):
    customer = _customer(db_session, "Risk Plain")
    result = customer_risk_service.assess_customer(db_session, customer)
    assert (result["risk_score"], result["risk_level"], result["factors"], result["changed"]) == (0, "LOW", [], False)


def test_screening_flags_and_alerts_add_up(db_session):
    pep = _customer(db_session, "Risk Pep", pep_flag=True)
    assert customer_risk_service.assess_customer(db_session, pep)["risk_level"] == "MEDIUM"  # PEP alone: 40

    db_session.add(Alert(customer_id=pep.id, risk_score=95, triggered_rules={"rules": ["R005"]}))
    result = customer_risk_service.assess_customer(db_session, pep)
    assert (result["risk_score"], result["risk_level"]) == (75, "HIGH")  # PEP 40 + high alert 35
    assert _factors(db_session, pep) == {"Politically exposed person", "Unresolved alert with a risk score of 80 or more"}

    sanctioned = _customer(db_session, "Risk Sanctioned", sanctions_flag=True)
    assert customer_risk_service.assess_customer(db_session, sanctioned)["risk_level"] == "HIGH"

    abroad = _customer(db_session, "Risk Abroad", residency_country="IR", adverse_media_flag=True)
    result = customer_risk_service.assess_customer(db_session, abroad)
    assert (result["risk_score"], result["risk_level"]) == (50, "MEDIUM")


def test_alert_volume_and_score_bands(db_session):
    customer = _customer(db_session, "Risk Busy")
    db_session.add_all(Alert(customer_id=customer.id, risk_score=65) for _ in range(10))
    result = customer_risk_service.assess_customer(db_session, customer)
    assert (result["risk_score"], result["risk_level"]) == (30, "LOW")  # medium alert 20 + volume 10

    db_session.add(Alert(customer_id=customer.id, risk_score=40, status="RESOLVED"))  # resolved alerts do not count
    assert customer_risk_service.assess_customer(db_session, customer)["risk_score"] == 30


def test_rating_change_is_audited_and_factors_are_replaced(db_session):
    customer = _customer(db_session, "Risk Audited", pep_flag=True)
    customer_risk_service.assess_customer(db_session, customer)
    db_session.commit()
    audit = db_session.query(AuditLog).filter_by(entity_type="CUSTOMER", entity_id=customer.id, action="UPDATE").one()
    assert audit.old_values["risk_level"] == "LOW" and audit.new_values["risk_level"] == "MEDIUM"

    customer.pep_flag = False
    result = customer_risk_service.assess_customer(db_session, customer)
    assert (result["risk_level"], result["previous_risk_level"], result["changed"]) == ("LOW", "MEDIUM", True)
    assert _factors(db_session, customer) == set()


def test_resolving_the_last_alert_lowers_the_rating(client, auth_headers, compliance_headers, db_session):
    customer = _customer(db_session, "Risk Resolved")
    alert = Alert(customer_id=customer.id, risk_score=90, triggered_rules={"rules": ["R001"]})
    db_session.add(alert)
    db_session.commit()

    resp = client.post(f"/api/v1/customers/{customer.id}/risk-assessment", headers=auth_headers)
    assert resp.status_code == 200
    assert (resp.json()["risk_level"], resp.json()["factors"][0]["weight"]) == ("MEDIUM", 35)

    resolved = client.put(
        f"/api/v1/alerts/{alert.id}/resolve",
        json={"outcome": "FALSE_POSITIVE", "reasons": ["RULE_TOO_BROAD"], "resolution_notes": "Not relevant"},
        headers=compliance_headers,
    )
    assert resolved.status_code == 200
    assert client.get(f"/api/v1/customers/{customer.id}", headers=auth_headers).json()["risk_level"] == "LOW"


def test_sar_filing_keeps_the_customer_elevated(client, compliance_headers, auth_headers, db_session):
    customer = _customer(db_session, "Risk Sar")
    alert = Alert(customer_id=customer.id, risk_score=90, triggered_rules={"rules": ["R001"]})
    db_session.add(alert)
    db_session.commit()
    client.put(
        f"/api/v1/alerts/{alert.id}/resolve",
        json={"outcome": "SAR_FILED", "reasons": ["STRUCTURING_SUSPECTED"], "resolution_notes": "Filed"},
        headers=compliance_headers,
    )
    body = client.get(f"/api/v1/customers/{customer.id}", headers=auth_headers).json()
    assert (body["risk_score"], body["risk_level"]) == (50, "MEDIUM")


def test_new_alert_from_a_transaction_updates_the_rating(client, auth_headers):
    from datetime import datetime, timezone

    customer = client.post(
        "/api/v1/customers", json={"full_name": "Risk Txn Corp", "email": "risk.txn@example.com", "customer_type": "CORPORATE"},
        headers=auth_headers,
    ).json()
    client.put(f"/api/v1/customers/{customer['id']}", json={"sanctions_flag": True}, headers=auth_headers)
    account = client.post(
        "/api/v1/accounts", json={"customer_id": customer["id"], "account_type": "CHECKING", "balance": 1000}, headers=auth_headers
    ).json()
    client.post(
        "/api/v1/transactions",
        json={"customer_id": customer["id"], "account_id": account["id"], "transaction_type": "TRANSFER", "amount": 500,
              "transaction_date": datetime.now(timezone.utc).isoformat()},
        headers=auth_headers,
    )
    body = client.get(f"/api/v1/customers/{customer['id']}", headers=auth_headers).json()
    assert body["risk_level"] == "HIGH" and body["risk_score"] == 100
    profile = client.get(f"/api/v1/customers/{customer['id']}/risk-profile", headers=auth_headers).json()
    assert "Sanctions list match" in {p["risk_factor"] for p in profile}


def test_assess_all_requires_compliance_or_admin(client, auth_headers, compliance_headers, db_session):
    customer = _customer(db_session, "Risk Bulk", pep_flag=True)
    assert client.post("/api/v1/customers/risk-assessment", headers=auth_headers).status_code == 403

    resp = client.post("/api/v1/customers/risk-assessment", headers=compliance_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["changed"] >= 1 and sum(body["by_level"].values()) == body["customers"]
    db_session.refresh(customer)
    assert customer.risk_level == "MEDIUM"
