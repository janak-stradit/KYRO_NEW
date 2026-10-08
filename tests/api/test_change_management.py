"""
tests/api/test_change_management.py — Regulatory change management (Phase 11.5):
change detection with impact, and maker-checker rule changes with effective dates.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.alert import Alert
from app.models.change_management import RuleConfigChange
from app.models.customer import Customer
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.regulatory import RegulatorySection
from app.models.transaction import Transaction
from app.config import get_settings
from app.services import change_service, rule_config_service
from app.services.regulatory_ingestion_service import ingest_source

from .test_regulatory import _xml, feed, source  # noqa: F401  (shared eCFR fixtures)

pytestmark = pytest.mark.db

TODAY = date.today()


def _effective_amount(client, headers) -> float:
    return client.get("/api/v1/rule-configs/effective", headers=headers).json()["AMOUNT_THRESHOLD"]


def _propose(client, headers, **overrides):
    payload = {
        "key": "AMOUNT_THRESHOLD", "value": 12345,
        "reason": "Align the threshold with the amended reporting rule", "effective_from": TODAY.isoformat(),
        **overrides,
    }
    return client.post("/api/v1/changes/rules", json=payload, headers=headers)


@pytest.fixture(autouse=True)
def _fresh_rule_cache():
    rule_config_service.invalidate_cache()
    yield
    rule_config_service.invalidate_cache()


# ── Regulatory change detection and impact ───────────────────────────────

def test_amended_section_creates_a_change_with_its_impact(client, auth_headers, compliance_headers, db_session, source, feed):
    ingest_source(db_session, source)
    assert client.get("/api/v1/changes/regulatory", headers=auth_headers).json() == [] or all(
        c["source_id"] != str(source.id) for c in client.get("/api/v1/changes/regulatory", headers=auth_headers).json()
    )  # the first load is not a change

    # A confirmed obligation on the widget section, mapped to the amount rule
    section = db_session.query(RegulatorySection).filter_by(source_id=source.id, section_ref="99 CFR 9999.10").one()
    obligation = Obligation(
        section_id=section.id, section_ref=section.section_ref, section_version=section.version,
        obligated_party="A widget dealer", action="report each widget transfer of more than $7,500",
        category="REPORTING", status="CONFIRMED", extracted_by="mock", quote_verified=True,
    )
    db_session.add(obligation)
    db_session.flush()
    db_session.add(ObligationMapping(obligation_id=obligation.id, control_code="R001", status="CONFIRMED", proposed_by="user"))
    db_session.commit()

    feed.update(xml=_xml(widget_limit="$10,000", include_gadgets=False), amended={"9999.10": "2026-09-15"})
    ingest_source(db_session, source)

    changes = [c for c in client.get("/api/v1/changes/regulatory", headers=auth_headers).json() if c["source_id"] == str(source.id)]
    by_ref = {c["section_ref"]: c for c in changes}
    assert {ref: c["change_type"] for ref, c in by_ref.items()} == {"99 CFR 9999.10": "AMENDED", "99 CFR 9999.20": "REMOVED"}

    amended = by_ref["99 CFR 9999.10"]
    assert (amended["status"], amended["old_version"], amended["new_version"]) == ("OPEN", "2024-03-01", "2026-09-15")
    assert [o["action"] for o in amended["affected"]["obligations"]] == ["report each widget transfer of more than $7,500"]
    assert amended["affected"]["controls"] == [{"code": "R001", "name": "Amount Threshold"}]
    assert amended["affected"]["config_keys"] == ["AMOUNT_THRESHOLD"]

    detail = client.get(f"/api/v1/changes/regulatory/{amended['id']}", headers=auth_headers).json()
    removed = [d["text"] for d in detail["diff"] if d["op"] == "removed"]
    added = [d["text"] for d in detail["diff"] if d["op"] == "added"]
    assert any("$7,500" in t for t in removed) and any("$10,000" in t for t in added)

    # Assessing the change is a compliance decision
    url = f"/api/v1/changes/regulatory/{amended['id']}/assess"
    assert client.put(url, json={"status": "ACTION_REQUIRED"}, headers=auth_headers).status_code == 403
    resp = client.put(url, json={"status": "ACTION_REQUIRED", "notes": "Threshold rises"}, headers=compliance_headers)
    assert resp.status_code == 200 and resp.json()["status"] == "ACTION_REQUIRED" and resp.json()["assessed_by"]

    # A rule change can be raised against the regulatory change that caused it
    proposal = _propose(client, compliance_headers, value=10000.5, regulatory_change_id=amended["id"])
    assert proposal.status_code == 201 and proposal.json()["regulatory_change_id"] == amended["id"]


# ── Maker-checker rule changes ───────────────────────────────────────────

def test_proposer_cannot_approve_their_own_change(client, compliance_headers, admin_headers, auth_headers):
    before = _effective_amount(client, compliance_headers)
    assert _propose(client, auth_headers).status_code == 403  # analysts cannot propose

    resp = _propose(client, compliance_headers)
    assert resp.status_code == 201, resp.text
    change = resp.json()
    assert (change["status"], change["previous_value"], change["proposed_value"]) == ("PENDING_APPROVAL", {"value": before}, {"value": 12345})
    assert change["proposed_by_name"] and change["backtest"]["available"] is True

    url = f"/api/v1/changes/rules/{change['id']}/review"
    own = client.put(url, json={"decision": "APPROVED"}, headers=compliance_headers)
    assert own.status_code == 403 and "someone other than" in own.json()["detail"]
    assert _effective_amount(client, compliance_headers) == before  # nothing changed yet

    # A second change to the same setting has to wait
    assert _propose(client, admin_headers, value=20000).status_code == 409

    approved = client.put(url, json={"decision": "APPROVED", "notes": "Agreed"}, headers=admin_headers)
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "ACTIVE" and body["activated_at"] and body["reviewed_by_name"]
    assert _effective_amount(client, compliance_headers) == 12345

    # Decided changes are final
    assert client.put(url, json={"decision": "REJECTED", "notes": "Too late"}, headers=admin_headers).status_code == 409


def test_rejection_needs_a_reason_and_leaves_the_rule_alone(client, compliance_headers, admin_headers):
    before = _effective_amount(client, compliance_headers)
    change = _propose(client, compliance_headers).json()
    url = f"/api/v1/changes/rules/{change['id']}/review"

    assert client.put(url, json={"decision": "REJECTED"}, headers=admin_headers).status_code == 422
    rejected = client.put(url, json={"decision": "REJECTED", "notes": "Backtest loses true positives"}, headers=admin_headers)
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert rejected.json()["review_notes"] == "Backtest loses true positives"
    assert _effective_amount(client, compliance_headers) == before


def test_future_dated_change_waits_for_its_effective_date(client, compliance_headers, admin_headers, db_session):
    before = _effective_amount(client, compliance_headers)
    change = _propose(client, compliance_headers, effective_from=(TODAY + timedelta(days=30)).isoformat()).json()
    approved = client.put(f"/api/v1/changes/rules/{change['id']}/review", json={"decision": "APPROVED"}, headers=admin_headers)
    assert approved.json()["status"] == "APPROVED" and approved.json()["activated_at"] is None
    assert _effective_amount(client, compliance_headers) == before
    assert change_service.activate_due(db_session) == 0

    # The effective date arrives
    row = db_session.get(RuleConfigChange, change["id"])
    row.effective_from = TODAY
    db_session.commit()
    listed = client.get("/api/v1/changes/rules", headers=compliance_headers).json()  # listing applies due changes
    assert next(c for c in listed if c["id"] == change["id"])["status"] == "ACTIVE"
    rule_config_service.invalidate_cache()
    assert _effective_amount(client, compliance_headers) == 12345


def test_proposer_can_withdraw_and_invalid_changes_are_refused(client, compliance_headers, admin_headers):
    current = _effective_amount(client, compliance_headers)
    assert _propose(client, compliance_headers, value=current).status_code == 409  # no-op
    assert _propose(client, compliance_headers, key="NOT_A_KEY").status_code == 400
    assert _propose(client, compliance_headers, value="lots").status_code == 400
    assert _propose(client, compliance_headers, reason="short").status_code == 422

    change = _propose(client, compliance_headers).json()
    url = f"/api/v1/changes/rules/{change['id']}/review"
    assert client.put(url, json={"decision": "CANCELLED"}, headers=admin_headers).status_code == 403
    assert client.put(url, json={"decision": "CANCELLED"}, headers=compliance_headers).json()["status"] == "CANCELLED"
    assert _propose(client, compliance_headers).status_code == 201  # the setting is free again


def test_backtest_counts_transactions_and_missed_true_positives(client, compliance_headers, db_session):
    from app.models.account import Account

    customer = Customer(full_name="Backtest Ltd", email="backtest@example.com", customer_type="CORPORATE")
    db_session.add(customer)
    db_session.flush()
    account = Account(customer_id=customer.id, account_type="CHECKING", balance=0)
    db_session.add(account)
    db_session.flush()
    now = datetime.now(timezone.utc)
    for amount in (900_000_001, 900_000_002, 900_000_009):
        db_session.add(Transaction(customer_id=customer.id, account_id=account.id, transaction_type="TRANSFER", amount=amount, transaction_date=now))
    db_session.add(Alert(
        customer_id=customer.id, risk_score=90, triggered_rules={"rules": ["R001"]}, status="RESOLVED",
        resolution_outcome="SAR_FILED", is_false_positive=False, resolved_at=now,
    ))
    db_session.commit()

    # Raising the threshold from 900,000,000 to 900,000,005 stops flagging two of the three
    result = change_service.backtest(db_session, "AMOUNT_THRESHOLD", 900_000_000, 900_000_005)
    assert (result["transactions_flagged_now"], result["transactions_flagged_after"], result["difference"]) == (3, 1, -2)
    assert result["confirmed_true_positive_customers_missed"] == 1 and result["passes_recall_floor"] is False

    # Lowering it cannot miss anything that is caught today
    lowered = change_service.backtest(db_session, "AMOUNT_THRESHOLD", 900_000_005, 900_000_000)
    assert lowered["difference"] == 2 and lowered["passes_recall_floor"] is True

    other = change_service.backtest(db_session, "VELOCITY_DAILY_LIMIT", 5, 8)
    assert other["available"] is False

    preview = client.post("/api/v1/changes/rules/backtest", json={"key": "AMOUNT_THRESHOLD", "value": 900_000_005}, headers=compliance_headers)
    assert preview.status_code == 200 and preview.json()["backtest"]["available"] is True


def test_direct_threshold_edits_can_be_switched_off(client, compliance_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "rule_changes_require_approval", True)
    resp = client.put("/api/v1/rule-configs/AMOUNT_THRESHOLD", json={"value": 5}, headers=compliance_headers)
    assert resp.status_code == 409 and "change request" in resp.json()["detail"]
