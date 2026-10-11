"""
tests/api/test_sar_confidentiality.py — What roles without "sar.view" see of a
potential SAR: a general status, and none of the SAR content.
"""
import uuid
from datetime import timedelta

import pytest

from app.models.alert import Alert
from app.models.alert_note import AlertNote
from app.models.sar_narrative import SarNarrative
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _create_alert_via_sanctions_hit

pytestmark = pytest.mark.db

_NOTES = "Funds routed through a sanctioned bank; recommend SAR"


def _headers(client, db_session, role, name):
    user = _make_user(db_session, username=name, role=role)
    return _login(client, user.username), user


@pytest.fixture
def potential_sar(client, auth_headers, db_session):
    """A case an investigator noted, then escalated as a potential SAR, then noted again."""
    l2, _ = _headers(client, db_session, "L2_INVESTIGATOR", "conf.l2")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "conf.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    client.post(f"{url}/notes", json={"body": "Called the relationship manager"}, headers=l2)
    escalated = client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": _NOTES, "potential_sar": True},
                           headers=l2)
    assert escalated.status_code == 200
    client.post(f"{url}/notes", json={"body": "MLRO: draft the SAR for Friday"}, headers=_headers(client, db_session, "MLRO", "conf.mlro0")[0])
    # A test runs in one database transaction, so every note gets the same server time; date them as real requests would
    row = db_session.get(Alert, uuid.UUID(alert["id"]))
    for note in db_session.query(AlertNote).filter_by(alert_id=row.id):
        before = note.body.startswith("Called")
        note.created_at = row.sar_candidate_at + timedelta(minutes=-5 if before else 5)
    db_session.commit()
    return url, l2


def test_team_lead_follows_the_case_without_seeing_sar_content(client, db_session, potential_sar):
    url, _ = potential_sar
    lead, _ = _headers(client, db_session, "TEAM_LEAD", "conf.lead")
    mlro, _ = _headers(client, db_session, "MLRO", "conf.mlro")

    seen = client.get(url, headers=lead).json()
    assert seen["compliance_status"] == "WITH_MLRO" and seen["restricted"] is True
    assert seen["resolution_notes"] is None and seen["resolution_reasons"] is None
    assert seen["potential_sar"] is None  # not even the flag

    full = client.get(url, headers=mlro).json()
    assert full["restricted"] is False and full["potential_sar"] is True and full["resolution_notes"] == _NOTES

    # The queue masks the same way
    item = next(a for a in client.get("/api/v1/alerts/queue", params={"status_filter": "ALL"}, headers=lead).json()["items"]
                if a["id"] == seen["id"])
    assert item["resolution_notes"] is None and item["compliance_status"] == "WITH_MLRO"


def test_timeline_withholds_notes_and_decisions_after_the_escalation(client, db_session, potential_sar):
    url, _ = potential_sar
    lead, _ = _headers(client, db_session, "TEAM_LEAD", "conf.lead2")
    mlro, _ = _headers(client, db_session, "MLRO", "conf.mlro2")

    def details(headers):
        events = client.get(f"{url}/timeline", headers=headers).json()["events"]
        return {e["kind"]: e for e in events if e["kind"] in ("escalated",)}, [e["detail"] for e in events if e["kind"] == "note"]

    lead_view, lead_notes = details(lead)
    assert lead_notes == ["Called the relationship manager"]
    assert lead_view["escalated"]["title"] == "Passed to the MLRO" and lead_view["escalated"]["detail"] is None

    mlro_view, mlro_notes = details(mlro)
    assert set(mlro_notes) == {"Called the relationship manager", "MLRO: draft the SAR for Friday"}
    assert "Sanctions" in mlro_view["escalated"]["title"]


def test_narratives_are_versioned_and_restricted_once_escalated(client, auth_headers, db_session):
    l2, _ = _headers(client, db_session, "L2_INVESTIGATOR", "nar.l2")
    mlro, _ = _headers(client, db_session, "MLRO", "nar.mlro")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "nar.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    # Before escalation the investigator drafts and edits; each save is a new version
    assert client.post(f"{url}/narratives", json={"text": "First version", "confirmed": True}, headers=l2).json()["version"] == 1
    assert client.post(f"{url}/narratives", json={"text": "Second version", "confirmed": True}, headers=l2).json()["version"] == 2
    versions = client.get(f"{url}/narratives", headers=l2).json()["versions"]
    assert [v["text"] for v in versions] == ["Second version", "First version"]

    client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"], "potential_sar": True}, headers=l2)
    assert client.get(f"{url}/narratives", headers=l2).json() == {"restricted": True, "versions": []}
    assert client.post(f"{url}/narratives", json={"text": "Third", "confirmed": True}, headers=l2).status_code == 403
    assert client.post(f"{url}/summary", headers=l2).status_code == 403
    assert client.post(f"{url}/draft-narrative", headers=l2).status_code == 403

    # The MLRO carries on; nothing earlier was overwritten
    assert client.post(f"{url}/narratives", json={"text": "MLRO final", "confirmed": True}, headers=mlro).json()["version"] == 3
    rows = db_session.query(SarNarrative).filter_by(alert_id=uuid.UUID(alert["id"])).order_by(SarNarrative.version).all()
    assert [r.text for r in rows] == ["First version", "Second version", "MLRO final"]


def test_ordinary_escalation_is_not_restricted(client, auth_headers, db_session):
    l2, _ = _headers(client, db_session, "L2_INVESTIGATOR", "ord.l2")
    lead, _ = _headers(client, db_session, "TEAM_LEAD", "ord.lead")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "ord.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Needs a second look"}, headers=l2)
    seen = client.get(url, headers=lead).json()
    assert seen["restricted"] is False and seen["resolution_notes"] == "Needs a second look"
    assert seen["compliance_status"] == "WITH_MLRO"


def test_mlro_dashboard_counts_sar_deadlines(client, db_session, potential_sar):
    mlro, _ = _headers(client, db_session, "MLRO", "conf.mlro3")
    counts = client.get("/api/v1/dashboard/my-work", headers=mlro).json()["sar_deadlines"]
    assert counts["open"] == 1 and counts["decisions_overdue"] == 0 and counts["filings_overdue"] == 0
