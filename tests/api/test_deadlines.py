"""
tests/api/test_deadlines.py — Case SLA, potential-SAR decision clock and SAR
filing deadline (services/deadline_service.py).
"""
import uuid
from datetime import timedelta

import pytest

from app.models.alert import Alert
from app.services import deadline_service
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _create_alert_via_sanctions_hit
from tests.api.test_change_management import _propose

pytestmark = pytest.mark.db


def _headers(client, db_session, role, name):
    return _login(client, _make_user(db_session, username=name, role=role).username)


def test_new_alerts_start_their_case_clock_from_policy(client, auth_headers, db_session):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "clock.start@example.com")
    row = db_session.get(Alert, uuid.UUID(alert["id"]))
    expected = deadline_service.defaults()["CASE_SLA_DAYS"][deadline_service.band(row.risk_score)]
    assert row.sla_days == expected and row.detected_at is not None
    assert row.sar_candidate_at is None and row.filing_due_at is None


def test_potential_sar_starts_a_shorter_clock_and_a_filing_deadline(client, auth_headers, db_session):
    l2 = _headers(client, db_session, "L2_INVESTIGATOR", "dl.l2")
    mlro = _headers(client, db_session, "MLRO", "dl.mlro")
    lead = _headers(client, db_session, "TEAM_LEAD", "dl.lead")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "clock.sar@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    escalated = client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"], "potential_sar": True}, headers=l2)
    assert escalated.status_code == 200
    row = db_session.get(Alert, uuid.UUID(alert["id"]))
    rules = deadline_service.defaults()
    assert row.sar_decision_days == rules["SAR_DECISION_DAYS"]
    assert row.filing_due_at == row.detected_at + timedelta(days=rules["SAR_FILING_DAYS"])

    clocks = client.get(f"{url}/deadlines", headers=mlro).json()
    assert clocks["case"]["status"] == "ON_TRACK"
    assert clocks["sar"]["potential_sar"] is True
    assert clocks["sar"]["decision"]["status"] == "ON_TRACK" and clocks["sar"]["filing"]["status"] == "OPEN"
    # Roles that do not see SAR work get the case SLA only
    assert "sar" not in client.get(f"{url}/deadlines", headers=lead).json()

    # Missing the MLRO decision date makes the case overdue, whatever its case SLA
    row.sar_candidate_at = row.sar_candidate_at - timedelta(days=rules["SAR_DECISION_DAYS"] + 1)
    db_session.commit()
    queue = {a["id"]: a for a in client.get("/api/v1/alerts/queue", params={"attention": "overdue"}, headers=mlro).json()["items"]}
    assert alert["id"] in queue and queue[alert["id"]]["overdue"] is True
    assert client.get(f"{url}/deadlines", headers=mlro).json()["sar"]["decision"]["status"] == "OVERDUE"

    # Filing within the deadline is recorded as such
    client.put(f"{url}/resolve", json={"outcome": "SAR_FILED", "reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Filed",
                                       "sar_reference": "SAR-77"}, headers=mlro)
    filing = client.get(f"{url}/deadlines", headers=mlro).json()["sar"]
    assert filing["filing"]["status"] == "FILED" and filing["decision"]["status"] == "MISSED"


def test_a_policy_change_applies_to_new_cases_not_running_ones(client, auth_headers, compliance_headers, mlro_headers, db_session):
    before = _create_alert_via_sanctions_hit(client, auth_headers, "clock.before@example.com")
    old = db_session.get(Alert, uuid.UUID(before["id"]))
    band = deadline_service.band(old.risk_score)
    sla = dict(deadline_service.defaults()["CASE_SLA_DAYS"])
    sla[band] = sla[band] + 7

    proposed = _propose(client, compliance_headers, key="CASE_SLA_DAYS", value=sla)
    assert proposed.status_code == 201, proposed.text
    review = client.put(f"/api/v1/changes/rules/{proposed.json()['id']}/review", json={"decision": "APPROVED"}, headers=mlro_headers)
    assert review.json()["status"] == "ACTIVE"

    after = _create_alert_via_sanctions_hit(client, auth_headers, "clock.after@example.com")
    assert db_session.get(Alert, uuid.UUID(after["id"])).sla_days == sla[band]
    db_session.refresh(old)
    assert old.sla_days == deadline_service.defaults()["CASE_SLA_DAYS"][band]


@pytest.mark.parametrize("key, value", [
    ("CASE_SLA_DAYS", {"HIGH": 5, "MEDIUM": 10}),
    ("CASE_SLA_DAYS", {"HIGH": 0, "MEDIUM": 10, "LOW": 20}),
    ("SAR_DECISION_DAYS", "five"),
    ("SAR_FILING_DAYS", 0),
    ("DEADLINE_WARNING_PERCENT", 100),
])
def test_invalid_deadline_policies_are_refused(client, compliance_headers, key, value):
    assert _propose(client, compliance_headers, key=key, value=value).status_code == 400


def test_no_fixed_filing_deadline_is_allowed(client, compliance_headers):
    assert _propose(client, compliance_headers, key="SAR_FILING_DAYS", value=None).status_code == 201
