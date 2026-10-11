"""
tests/api/test_case_file.py — Case notes and timeline, the customer's earlier
cases, and activity against the customer's own baseline.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.alert import Alert
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _FP_RESOLUTION, _create_alert_via_sanctions_hit
from tests.api.test_patterns import Book, days_ago

pytestmark = pytest.mark.db


def _earlier_alert(db, customer_id, *, rules, outcome=None, score=70) -> Alert:
    alert = Alert(
        customer_id=customer_id, risk_score=score, triggered_rules={"rules": rules},
        status="RESOLVED" if outcome else "OPEN", resolution_outcome=outcome,
        resolved_at=datetime.now(timezone.utc) if outcome else None, is_false_positive=outcome == "FALSE_POSITIVE" if outcome else None,
    )
    db.add(alert)
    db.commit()
    return alert


# ── Notes and timeline ───────────────────────────────────────────────────

def test_notes_and_decisions_appear_on_the_timeline(client, auth_headers, compliance_headers, analyst_user, compliance_user):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "timeline@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    first = client.get(f"{url}/timeline", headers=auth_headers).json()
    assert first["note_count"] == 0 and [e["kind"] for e in first["events"]] == ["created"]
    assert "R006" in first["events"][0]["detail"]

    assert client.post(f"{url}/notes", json={"body": "   "}, headers=auth_headers).status_code == 422
    note = client.post(f"{url}/notes", json={"body": "  Called the relationship manager.  "}, headers=auth_headers)
    assert note.status_code == 201 and note.json()["detail"] == "Called the relationship manager."
    assert note.json()["by"] == analyst_user.full_name

    client.put(f"{url}/assign", json={"assigned_to": str(analyst_user.id)}, headers=auth_headers)
    client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)

    timeline = client.get(f"{url}/timeline", headers=auth_headers).json()
    # One test is one database transaction, so every event carries the same
    # time here and the newest-first order cannot be checked; look up by kind.
    events = {e["kind"]: e for e in timeline["events"]}
    assert timeline["note_count"] == 1 and len(timeline["events"]) == 4
    assert set(events) == {"resolved", "assigned", "note", "created"}
    assert events["resolved"]["title"] == "Resolved: False positive (Screening name mismatch)"
    assert events["resolved"]["by"] == compliance_user.full_name
    assert events["resolved"]["detail"] == _FP_RESOLUTION["resolution_notes"]
    assert events["assigned"]["title"] == f"Assigned to {analyst_user.full_name}"
    assert events["note"]["detail"] == "Called the relationship manager."


def test_notes_need_case_access_and_a_role_that_can_write(client, auth_headers, db_session):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "notes.access@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    auditor = _login(client, _make_user(db_session, username="auditor.notes", role="AUDITOR").username)
    viewer = _login(client, _make_user(db_session, username="viewer.notes", role="EXECUTIVE_VIEWER").username)

    assert client.get(f"{url}/timeline", headers=auditor).status_code == 200
    assert client.post(f"{url}/notes", json={"body": "An auditor's note"}, headers=auditor).status_code == 403
    assert client.get(f"{url}/timeline", headers=viewer).status_code == 403
    assert client.get(f"/api/v1/alerts/{uuid.uuid4()}/timeline", headers=auth_headers).status_code == 404
    assert client.post(f"/api/v1/alerts/{uuid.uuid4()}/notes", json={"body": "x"}, headers=auth_headers).status_code == 404


# ── Earlier cases ────────────────────────────────────────────────────────

def test_case_history_summarises_how_earlier_alerts_ended(client, auth_headers, compliance_headers, db_session):
    current = _create_alert_via_sanctions_hit(client, auth_headers, "history@example.com")
    customer_id = uuid.UUID(current["customer_id"])
    _earlier_alert(db_session, customer_id, rules=["R006", "R007"], outcome="FALSE_POSITIVE")
    _earlier_alert(db_session, customer_id, rules=["R006"], outcome="FALSE_POSITIVE")
    _earlier_alert(db_session, customer_id, rules=["R006"], outcome="SAR_FILED")
    _earlier_alert(db_session, customer_id, rules=["R001"], outcome="TRUE_POSITIVE_NO_SAR")
    _earlier_alert(db_session, customer_id, rules=["R001"])  # still open

    data = client.get(f"/api/v1/customers/{customer_id}/case-history", params={"alert_id": current["id"]}, headers=compliance_headers).json()
    assert (data["total"], data["open"], data["resolved"]) == (5, 1, 4)  # the case being viewed is left out
    assert data["outcomes"] == {"FALSE_POSITIVE": 2, "SAR_FILED": 1, "TRUE_POSITIVE_NO_SAR": 1}
    same = {r["rule"]: r for r in data["same_rules"]}
    assert same["R006"] == {"rule": "R006", "resolved": 3, "false_positive": 2, "sar_filed": 1}
    assert len(data["recent"]) == 4 and all(r["id"] != current["id"] for r in data["recent"])

    without = client.get(f"/api/v1/customers/{customer_id}/case-history", headers=compliance_headers).json()
    assert without["total"] == 6 and without["same_rules"] == []
    assert client.get(f"/api/v1/customers/{uuid.uuid4()}/case-history", headers=auth_headers).status_code == 404


def test_first_time_customer_has_no_history(client, auth_headers):
    current = _create_alert_via_sanctions_hit(client, auth_headers, "first.time@example.com")
    data = client.get(
        f"/api/v1/customers/{current['customer_id']}/case-history", params={"alert_id": current["id"]}, headers=auth_headers
    ).json()
    assert data["total"] == 0 and data["recent"] == [] and data["outcomes"] == {}
    assert all(r["resolved"] == 0 for r in data["same_rules"]) and data["same_rules"]


# ── Activity against the baseline ────────────────────────────────────────

def test_activity_compares_the_last_30_days_with_the_previous_90(client, auth_headers, db_session):
    book = Book(db_session, "Activity Case").steady_baseline(n=9, amount=100)
    book.txn(days_ago(5), amount=950, counterparty="New Trading Ltd", country="GB")
    book.txn(days_ago(3), amount=120, counterparty="Regular Payee", country="DE")
    db_session.commit()

    data = client.get(f"/api/v1/customers/{book.customer.id}/activity", headers=auth_headers).json()
    assert data["enough_history"] is True
    assert len(data["buckets"]) == 12 and [b["current"] for b in data["buckets"]] == [False] * 9 + [True] * 3
    assert sum(b["transactions"] for b in data["buckets"] if b["current"]) == 2
    assert sum(b["transactions"] for b in data["buckets"] if not b["current"]) == 9

    comparison = data["comparison"]
    assert comparison["transactions"] == {"current": 2, "usual": 3.0}
    assert comparison["largest_amount"] == [{"currency": "USD", "current": 950.0, "previous": 100.0}]
    assert comparison["new_counterparties"] == ["New Trading Ltd"] and comparison["new_countries"] == ["DE"]

    findings = {f["pattern"]: f for f in data["findings"]}
    assert set(findings) == {"THRESHOLD_BREACH"} and findings["THRESHOLD_BREACH"]["label"] == "Unusual Amount"
    assert "950.00 USD" in findings["THRESHOLD_BREACH"]["evidence"]


def test_activity_for_a_customer_without_history(client, auth_headers, db_session):
    book = Book(db_session, "New Customer").txn(days_ago(2), amount=5000)
    db_session.commit()
    data = client.get(f"/api/v1/customers/{book.customer.id}/activity", headers=auth_headers).json()
    assert data["enough_history"] is False and data["findings"] == []
    assert data["comparison"]["transactions"] == {"current": 1, "usual": 0.0}
    assert data["comparison"]["largest_amount"] == [{"currency": "USD", "current": 5000.0, "previous": None}]
    assert client.get(f"/api/v1/customers/{uuid.uuid4()}/activity", headers=auth_headers).status_code == 404


def test_stage_tracker_follows_the_case(client, auth_headers, compliance_headers, analyst_user):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "stages@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    stages = lambda: {s["key"]: s for s in client.get(f"{url}/timeline", headers=compliance_headers).json()["stages"]}

    s = stages()
    assert list(s) == ["opened", "assigned", "investigation", "decision", "quality"]
    assert s["opened"]["done"] and s["assigned"]["current"] and not s["investigation"]["done"]

    client.put(f"{url}/assign", json={"assigned_to": str(analyst_user.id)}, headers=auth_headers)
    assert stages()["assigned"]["done"] and stages()["investigation"]["current"]

    client.post(f"{url}/notes", json={"body": "Reviewed the transfers."}, headers=auth_headers)
    assert stages()["investigation"]["done"] and stages()["decision"]["current"]

    client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"]}, headers=auth_headers)
    s = stages()
    assert list(s) == ["opened", "assigned", "investigation", "escalated", "decision", "quality"]
    assert s["escalated"]["done"] and s["decision"]["current"]

    client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)
    s = stages()
    assert s["decision"]["done"] and s["decision"]["detail"] == "False positive" and s["quality"]["current"]


def test_a_case_resolved_straight_away_skips_the_middle_stages(client, auth_headers, compliance_headers):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "stages.fast@example.com")
    client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)
    s = {x["key"]: x for x in client.get(f"/api/v1/alerts/{alert['id']}/timeline", headers=compliance_headers).json()["stages"]}
    assert s["assigned"]["skipped"] and not s["assigned"]["current"] and s["decision"]["done"] and s["quality"]["current"]
