"""
tests/api/test_access_control.py — Emergency access to a case, and second-
person approval of roles that can see SAR cases.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.access_control import EmergencyAccessGrant
from app.models.audit import AuditLog
from app.models.user import User
from app.permissions import ROLES, has_permission
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _create_alert_via_sanctions_hit

pytestmark = pytest.mark.db

_SAR = {"outcome": "SAR_FILED", "reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Confirmed exposure", "sar_reference": "SAR-9"}


def _user(client, db_session, role, name):
    user = _make_user(db_session, username=name, role=role)
    return _login(client, user.username), user


def _sar_case(client, auth_headers, mlro, email):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, email)
    assert client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_SAR, headers=mlro).status_code == 200
    return alert["id"]


# ── Emergency access ─────────────────────────────────────────────────────

def test_admin_reads_a_sar_case_only_through_approved_time_limited_access(client, auth_headers, admin_headers, admin_user, db_session):
    mlro, mlro_user = _user(client, db_session, "MLRO", "em.mlro")
    case_id = _sar_case(client, auth_headers, mlro, "em.case@example.com")
    url = f"/api/v1/alerts/{case_id}"
    assert client.get(url, headers=admin_headers).status_code == 404

    asked = client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "Investigating a data fault", "duration_minutes": 30},
                        headers=admin_headers)
    assert asked.status_code == 201, asked.text
    grant = asked.json()
    assert grant["status"] == "REQUESTED" and not grant["live"]
    assert client.get(url, headers=admin_headers).status_code == 404  # not until approved

    # The admin cannot approve their own request; the MLRO can
    decision = f"/api/v1/access/emergency/{grant['id']}/decision"
    assert client.put(decision, json={"decision": "APPROVED"}, headers=admin_headers).status_code == 403
    approved = client.put(decision, json={"decision": "APPROVED", "notes": "One hour max"}, headers=mlro)
    assert approved.status_code == 200 and approved.json()["live"] is True

    assert client.get(url, headers=admin_headers).status_code == 200
    # Read-only: the grant opens the case, not the actions on it
    assert client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"]}, headers=admin_headers).status_code == 403
    # Only the granted case
    other = _sar_case(client, auth_headers, mlro, "em.other@example.com")
    assert client.get(f"/api/v1/alerts/{other}", headers=admin_headers).status_code == 404

    uses = db_session.query(AuditLog).filter_by(entity_type="EMERGENCY_ACCESS", entity_id=uuid.UUID(grant["id"]), action="VIEW").all()
    assert len(uses) == 1 and uses[0].performed_by == admin_user.id

    # Once it expires, the case is closed again
    row = db_session.get(EmergencyAccessGrant, uuid.UUID(grant["id"]))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(url, headers=admin_headers).status_code == 404


def test_emergency_access_is_limited_revocable_and_needs_a_reason(client, auth_headers, admin_headers, db_session):
    mlro, _ = _user(client, db_session, "MLRO", "em2.mlro")
    case_id = _sar_case(client, auth_headers, mlro, "em2.case@example.com")
    ask = lambda **body: client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "Support ticket 4411", **body},
                                     headers=admin_headers)

    assert ask(duration_minutes=100_000).status_code == 422
    assert client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "short"}, headers=admin_headers).status_code == 422
    assert client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "Because I need it"},
                       headers=mlro).status_code == 403  # the MLRO already has access; no permission to ask

    grant = ask().json()
    assert ask().status_code == 409  # one open request per case
    client.put(f"/api/v1/access/emergency/{grant['id']}/decision", json={"decision": "APPROVED"}, headers=mlro)
    assert client.get(f"/api/v1/alerts/{case_id}", headers=admin_headers).status_code == 200

    ended = client.put(f"/api/v1/access/emergency/{grant['id']}/revoke", headers=admin_headers)
    assert ended.status_code == 200 and ended.json()["status"] == "REVOKED"
    assert client.get(f"/api/v1/alerts/{case_id}", headers=admin_headers).status_code == 404

    # Analysts cannot ask for emergency access at all
    assert client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "Curious about it"},
                       headers=auth_headers).status_code == 403


def test_requests_are_listed_to_approvers_and_their_owners(client, auth_headers, admin_headers, db_session):
    mlro, _ = _user(client, db_session, "MLRO", "em3.mlro")
    case_id = _sar_case(client, auth_headers, mlro, "em3.case@example.com")
    client.post("/api/v1/access/emergency", json={"alert_id": case_id, "reason": "Fault investigation"}, headers=admin_headers)

    assert len(client.get("/api/v1/access/emergency", headers=mlro).json()) == 1
    assert len(client.get("/api/v1/access/emergency", headers=admin_headers).json()) == 1
    assert client.get("/api/v1/access/emergency", headers=auth_headers).status_code == 403


# ── Roles that can see SAR cases ─────────────────────────────────────────

def test_sar_bearing_roles_need_the_mlros_approval(client, admin_headers, admin_user, db_session):
    mlro, _ = _user(client, db_session, "MLRO", "rg.mlro")
    new_user = {"username": "rg.new", "email": "rg.new@example.com", "full_name": "New Starter", "password": "Str0ngPass!123"}

    # A role that can see SAR cases is not granted at creation
    refused = client.post("/api/v1/users", json={**new_user, "role": "MLRO"}, headers=admin_headers)
    assert refused.status_code == 409 and "approval" in refused.json()["detail"]
    created = client.post("/api/v1/users", json={**new_user, "role": "TEAM_LEAD"}, headers=admin_headers)
    assert created.status_code == 201
    user_id = created.json()["id"]

    # Changing to such a role waits for approval; other changes apply now
    pending = client.put(f"/api/v1/users/{user_id}", json={"role": "AUDITOR", "full_name": "New Auditor"}, headers=admin_headers)
    assert pending.status_code == 202
    assert pending.json()["role"] == "TEAM_LEAD" and pending.json()["pending_role"] == "AUDITOR"
    assert pending.json()["full_name"] == "New Auditor"
    assert client.put(f"/api/v1/users/{user_id}", json={"role": "MLRO"}, headers=admin_headers).status_code == 409  # one at a time

    requests = client.get("/api/v1/access/role-requests", headers=mlro).json()
    request_id = next(r["id"] for r in requests if r["user_id"] == user_id)
    decision = f"/api/v1/access/role-requests/{request_id}/decision"
    assert client.put(decision, json={"decision": "APPROVED"}, headers=admin_headers).status_code == 403
    assert client.put(decision, json={"decision": "APPROVED"}, headers=mlro).json()["status"] == "APPROVED"
    assert db_session.get(User, uuid.UUID(user_id)).role == "AUDITOR"

    # Roles without SAR access are still changed directly
    assert client.put(f"/api/v1/users/{user_id}", json={"role": "L1_ANALYST"}, headers=admin_headers).status_code == 200


def test_the_person_receiving_a_role_cannot_approve_it(client, admin_headers, db_session):
    _, lead_user = _user(client, db_session, "TEAM_LEAD", "rg2.lead")
    mlro, mlro_user = _user(client, db_session, "MLRO", "rg2.mlro")
    second_mlro, _ = _user(client, db_session, "MLRO", "rg2.mlro2")
    # An MLRO asking for the auditor role for themselves: they cannot approve it
    client.put(f"/api/v1/users/{lead_user.id}", json={"role": "MLRO"}, headers=admin_headers)
    request_id = client.get("/api/v1/access/role-requests", headers=mlro).json()[0]["id"]
    assert client.put(f"/api/v1/access/role-requests/{request_id}/cancel", headers=admin_headers).json()["status"] == "CANCELLED"

    assert client.put(f"/api/v1/users/{mlro_user.id}", json={"role": "AUDITOR"}, headers=admin_headers).status_code == 202
    request_id = next(r["id"] for r in client.get("/api/v1/access/role-requests", headers=mlro).json() if r["status"] == "REQUESTED")
    assert client.put(f"/api/v1/access/role-requests/{request_id}/decision", json={"decision": "APPROVED"}, headers=mlro).status_code == 403
    rejected = client.put(f"/api/v1/access/role-requests/{request_id}/decision", json={"decision": "REJECTED", "notes": "Not needed"},
                          headers=second_mlro)
    assert rejected.json()["status"] == "REJECTED"
    assert db_session.get(User, mlro_user.id).role == "MLRO"


def test_first_sar_role_on_a_new_installation_is_granted_directly(client, admin_headers, db_session):
    # Nobody can approve yet (the demo users are seeded at start-up, so stand them down), so the first MLRO is created directly
    approvers = [code for code in ROLES if has_permission(code, "sar.grant_access")]
    db_session.query(User).filter(User.role.in_(approvers)).update({"is_active": False})
    db_session.commit()
    created = client.post("/api/v1/users", json={"username": "first.mlro", "email": "first.mlro@example.com", "full_name": "First MLRO",
                                                 "password": "Str0ngPass!123", "role": "MLRO"}, headers=admin_headers)
    assert created.status_code == 201 and created.json()["role"] == "MLRO"
