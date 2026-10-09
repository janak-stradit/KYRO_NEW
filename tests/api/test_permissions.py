"""
tests/api/test_permissions.py — Roles, permissions, user administration, the
audit log and the case quality check.
"""
import pytest

from app.models.audit import AuditLog
from app.permissions import PERMISSIONS, ROLES, has_permission, is_read_only
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _FP_RESOLUTION, _create_alert_via_sanctions_hit
from tests.api.test_change_management import _propose

pytestmark = pytest.mark.db

_SAR = {
    "outcome": "SAR_FILED", "reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Confirmed exposure", "sar_reference": "SAR-1",
}
_NO_SAR = {"outcome": "TRUE_POSITIVE_NO_SAR", "reasons": ["EXPECTED_ACTIVITY_DOCUMENTED"], "resolution_notes": "Documented"}
_NEW_USER = {
    "username": "new.mlro", "email": "new.mlro@example.com", "full_name": "New MLRO", "password": "Str0ngPass!123", "role": "MLRO",
}


def _headers(client, db_session, role, username=None):
    user = _make_user(db_session, username=username or f"{role.lower()}.user", role=role)
    return _login(client, user.username), user


# ── The model itself ─────────────────────────────────────────────────────

def test_admin_holds_every_permission_and_roles_keep_duties_apart():
    assert ROLES["ADMIN"].permissions == frozenset(PERMISSIONS)
    for role in ROLES.values():
        assert role.permissions <= set(PERMISSIONS)
        assert role.purpose and role.responsibilities and role.limits
    # Only the MLRO and the two all-round roles may approve a SAR or a rule change
    for permission in ("sar.approve", "rules.approve"):
        holders = {code for code in ROLES if has_permission(code, permission)}
        assert holders == {"ADMIN", "MLRO", "COMPLIANCE_OFFICER"}
    assert {code for code in ROLES if has_permission(code, "users.manage")} == {"ADMIN"}
    assert is_read_only("AUDITOR") and is_read_only("EXECUTIVE_VIEWER") and not is_read_only("L1_ANALYST")
    assert is_read_only("NO_SUCH_ROLE") and not has_permission("NO_SUCH_ROLE", "cases.view")


def test_me_reports_role_label_and_permissions(client, db_session):
    headers, _ = _headers(client, db_session, "L1_ANALYST")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"] == "L1_ANALYST" and me["role_label"] == "Level 1 Analyst"
    assert me["permissions"] == ["alerts.close_false_positive", "alerts.escalate", "cases.view"]


def test_role_definitions_are_listed(client, auth_headers):
    data = client.get("/api/v1/roles", headers=auth_headers).json()
    assert [r["code"] for r in data["roles"]] == list(ROLES)
    assert {p["code"] for p in data["permissions"]} == set(PERMISSIONS)


# ── Case decisions ───────────────────────────────────────────────────────

def test_level_one_analyst_clears_false_positives_only(client, auth_headers, db_session, analyst_user):
    l1, _ = _headers(client, db_session, "L1_ANALYST")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "l1.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    assert client.put(f"{url}/assign", json={"assigned_to": str(analyst_user.id)}, headers=l1).status_code == 403
    for body in (_SAR, _NO_SAR):
        refused = client.put(f"{url}/resolve", json=body, headers=l1)
        assert refused.status_code == 403 and body["outcome"] in refused.json()["detail"]
    assert client.get(url, headers=l1).json()["status"] != "RESOLVED"

    cleared = client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=l1)
    assert cleared.status_code == 200 and cleared.json()["resolution_outcome"] == "FALSE_POSITIVE"


def test_investigator_recommends_and_only_mlro_approves_a_sar(client, auth_headers, db_session):
    l2, _ = _headers(client, db_session, "L2_INVESTIGATOR")
    lead, _ = _headers(client, db_session, "TEAM_LEAD")
    mlro, _ = _headers(client, db_session, "MLRO")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "sar.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    assert client.put(f"{url}/resolve", json=_SAR, headers=l2).status_code == 403
    assert client.put(f"{url}/resolve", json=_SAR, headers=lead).status_code == 403
    escalated = client.put(f"{url}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Recommend SAR"}, headers=l2)
    assert escalated.status_code == 200 and escalated.json()["status"] == "ESCALATED"

    filed = client.put(f"{url}/resolve", json=_SAR, headers=mlro)
    assert filed.status_code == 200 and filed.json()["resolution_outcome"] == "SAR_FILED"


def test_kyc_analyst_cannot_resolve_alerts(client, auth_headers, db_session):
    kyc, _ = _headers(client, db_session, "KYC_ANALYST")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "kyc.case@example.com")
    assert client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_FP_RESOLUTION, headers=kyc).status_code == 403
    assert client.post(f"/api/v1/customers/{alert['customer_id']}/screen", headers=kyc).status_code == 200


# ── Read-only roles ──────────────────────────────────────────────────────

def test_auditor_reads_everything_and_changes_nothing(client, auth_headers, db_session):
    auditor, _ = _headers(client, db_session, "AUDITOR")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "audit.case@example.com")

    assert client.get("/api/v1/alerts/queue", headers=auditor).status_code == 200
    assert client.get(f"/api/v1/customers/{alert['customer_id']}", headers=auditor).status_code == 200
    assert client.get("/api/v1/audit-logs", headers=auditor).status_code == 200

    for method, url, body in (
        ("put", f"/api/v1/alerts/{alert['id']}/resolve", _FP_RESOLUTION),
        ("put", f"/api/v1/customers/{alert['customer_id']}", {"full_name": "Changed"}),
        ("post", "/api/v1/customers", {"full_name": "X", "email": "x@example.com", "customer_type": "INDIVIDUAL"}),
        ("post", "/api/v1/regulatory/ask", {"question": "What must a broker-dealer report?"}),
        ("post", "/api/v1/users", _NEW_USER),
    ):
        refused = getattr(client, method)(url, json=body, headers=auditor)
        assert refused.status_code == 403, (url, refused.text)
    # Signing out is still possible
    assert client.post("/api/v1/auth/logout", headers=auditor).status_code == 200


def test_executive_viewer_sees_totals_but_no_records(client, auth_headers, db_session):
    viewer, _ = _headers(client, db_session, "EXECUTIVE_VIEWER")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "exec.case@example.com")

    for url in ("/api/v1/dashboard/kpis", "/api/v1/dashboard/charts", "/api/v1/dashboard/patterns"):
        assert client.get(url, headers=viewer).status_code == 200, url
    for url in (
        "/api/v1/dashboard/recent-alerts", "/api/v1/dashboard/patterns/customers",
        "/api/v1/alerts/queue", f"/api/v1/alerts/{alert['id']}", "/api/v1/customers", f"/api/v1/customers/{alert['customer_id']}",
        "/api/v1/transactions", "/api/v1/kyc-reviews", f"/api/v1/documents?customer_id={alert['customer_id']}", "/api/v1/audit-logs",
    ):
        assert client.get(url, headers=viewer).status_code == 403, url


# ── Quality check ────────────────────────────────────────────────────────

def test_quality_check_is_recorded_by_someone_else(client, auth_headers, db_session):
    mlro, _ = _headers(client, db_session, "MLRO")
    qa, qa_user = _headers(client, db_session, "QA_REVIEWER")
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "qa.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}"

    assert client.put(f"{url}/qa", json={"result": "PASS"}, headers=qa).status_code == 409  # not resolved yet
    client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=mlro)

    assert client.put(f"{url}/qa", json={"result": "PASS"}, headers=auth_headers).status_code == 403  # no permission
    own = client.put(f"{url}/qa", json={"result": "PASS"}, headers=mlro)
    assert own.status_code == 403 and "someone other than" in own.json()["detail"]
    assert client.put(f"{url}/qa", json={"result": "FAIL"}, headers=qa).status_code == 422  # a fail needs notes

    failed = client.put(f"{url}/qa", json={"result": "FAIL", "notes": "No evidence attached"}, headers=qa)
    assert failed.status_code == 200
    body = failed.json()
    assert body["qa_result"] == "FAIL" and body["qa_by"] == str(qa_user.id) and body["qa_at"]
    assert body["resolution_outcome"] == "FALSE_POSITIVE" and body["status"] == "RESOLVED"  # the outcome is untouched
    queue = lambda status: [a["id"] for a in client.get("/api/v1/alerts/queue", params={"status_filter": status}, headers=qa).json()["items"]]
    assert queue("QA_FAILED") == [alert["id"]] and queue("AWAITING_QA") == []
    # The QA reviewer cannot change the outcome
    assert client.put(f"{url}/resolve", json=_FP_RESOLUTION, headers=qa).status_code == 403


# ── Rule changes ─────────────────────────────────────────────────────────

def test_rules_owner_proposes_and_mlro_approves(client, db_session):
    owner, _ = _headers(client, db_session, "RULES_OWNER")
    other_owner, _ = _headers(client, db_session, "RULES_OWNER", username="rules.second")
    mlro, _ = _headers(client, db_session, "MLRO")
    l2, _ = _headers(client, db_session, "L2_INVESTIGATOR")

    assert _propose(client, l2).status_code == 403
    change = _propose(client, owner)
    assert change.status_code == 201, change.text
    url = f"/api/v1/changes/rules/{change.json()['id']}/review"

    # A second rules owner is a different person but still has no approval permission
    refused = client.put(url, json={"decision": "APPROVED"}, headers=other_owner)
    assert refused.status_code == 403 and "approval permission" in refused.json()["detail"]
    approved = client.put(url, json={"decision": "APPROVED"}, headers=mlro)
    assert approved.status_code == 200 and approved.json()["status"] in ("APPROVED", "ACTIVE")


def test_rules_owner_can_withdraw_their_own_proposal(client, db_session):
    owner, _ = _headers(client, db_session, "RULES_OWNER")
    change = _propose(client, owner).json()
    withdrawn = client.put(f"/api/v1/changes/rules/{change['id']}/review", json={"decision": "CANCELLED"}, headers=owner)
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "CANCELLED"


# ── User administration ──────────────────────────────────────────────────

def test_admin_creates_a_user_who_can_sign_in(client, admin_headers, admin_user, db_session):
    created = client.post("/api/v1/users", json=_NEW_USER, headers=admin_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "MLRO" and body["is_active"] is True and "password" not in body and "hashed_password" not in body

    login = client.post("/api/v1/auth/login", data={"username": "new.mlro", "password": "Str0ngPass!123"})
    assert login.status_code == 200
    assert any(u["username"] == "new.mlro" for u in client.get("/api/v1/users", headers=admin_headers).json())

    entry = db_session.query(AuditLog).filter_by(entity_type="USER", action="CREATE").one()
    assert entry.performed_by == admin_user.id and entry.new_values == {"username": "new.mlro", "role": "MLRO"}


@pytest.mark.parametrize("change, status_code", [
    ({"role": "SUPERUSER"}, 422),
    ({"password": "short"}, 422),
    ({"username": "has space"}, 422),
    ({"email": "not-an-email"}, 422),
    ({"email": "new.mlro@kyro.local"}, 201),
])
def test_invalid_users_are_rejected(client, admin_headers, change, status_code):
    assert client.post("/api/v1/users", json={**_NEW_USER, **change}, headers=admin_headers).status_code == status_code


def test_duplicate_users_are_rejected(client, admin_headers):
    assert client.post("/api/v1/users", json=_NEW_USER, headers=admin_headers).status_code == 201
    same_name = client.post("/api/v1/users", json={**_NEW_USER, "username": "NEW.MLRO", "email": "other@example.com"}, headers=admin_headers)
    same_email = client.post("/api/v1/users", json={**_NEW_USER, "username": "someone.else"}, headers=admin_headers)
    assert same_name.status_code == 409 and same_email.status_code == 409


def test_only_administrators_manage_users(client, compliance_headers, db_session):
    mlro, _ = _headers(client, db_session, "MLRO")
    for headers in (compliance_headers, mlro):
        assert client.get("/api/v1/users", headers=headers).status_code == 403
        assert client.post("/api/v1/users", json=_NEW_USER, headers=headers).status_code == 403


def test_role_change_takes_effect_and_is_audited(client, admin_headers, auth_headers, analyst_user, db_session):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "role.change@example.com")
    url = f"/api/v1/alerts/{alert['id']}/resolve"
    assert client.put(url, json=_FP_RESOLUTION, headers=auth_headers).status_code == 403

    updated = client.put(f"/api/v1/users/{analyst_user.id}", json={"role": "TEAM_LEAD"}, headers=admin_headers)
    assert updated.status_code == 200 and updated.json()["role"] == "TEAM_LEAD"
    # Same token: the permission follows the stored role, not the token
    assert client.put(url, json=_FP_RESOLUTION, headers=auth_headers).status_code == 200

    entry = db_session.query(AuditLog).filter_by(entity_type="USER", action="UPDATE", entity_id=analyst_user.id).one()
    assert entry.old_values == {"role": "ANALYST"} and entry.new_values == {"role": "TEAM_LEAD"}


def test_deactivated_user_is_locked_out(client, admin_headers, auth_headers, analyst_user):
    assert client.put(f"/api/v1/users/{analyst_user.id}", json={"is_active": False}, headers=admin_headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401
    login = client.post("/api/v1/auth/login", data={"username": analyst_user.username, "password": "Str0ngPass!123"})
    assert login.status_code == 403


def test_password_reset_replaces_the_old_password(client, admin_headers, analyst_user):
    url = f"/api/v1/users/{analyst_user.id}/reset-password"
    assert client.post(url, json={"password": "short"}, headers=admin_headers).status_code == 422
    assert client.post(url, json={"password": "An0ther!Passw0rd"}, headers=admin_headers).status_code == 204
    login = lambda password: client.post("/api/v1/auth/login", data={"username": analyst_user.username, "password": password})
    assert login("Str0ngPass!123").status_code == 401 and login("An0ther!Passw0rd").status_code == 200


def test_the_last_administrator_cannot_be_removed(client, admin_headers, admin_user, db_session):
    url = f"/api/v1/users/{admin_user.id}"
    for change in ({"role": "MLRO"}, {"is_active": False}):
        own = client.put(url, json=change, headers=admin_headers)
        assert own.status_code == 409 and "your own" in own.json()["detail"]

    second_headers, second = _headers(client, db_session, "ADMIN", username="admin2")
    # With two administrators, one may demote the other...
    assert client.put(url, json={"role": "MLRO"}, headers=second_headers).status_code == 200
    # ...and the one left cannot then be removed by anyone
    assert client.put(f"/api/v1/users/{second.id}", json={"role": "MLRO"}, headers=second_headers).status_code == 409
    assert client.put(f"/api/v1/users/{second.id}", json={"full_name": "Second Admin"}, headers=second_headers).status_code == 200


def test_audit_log_is_filtered_and_names_the_actor(client, admin_headers, admin_user, auth_headers):
    client.post("/api/v1/users", json=_NEW_USER, headers=admin_headers)
    assert client.get("/api/v1/audit-logs", headers=auth_headers).status_code == 403

    data = client.get("/api/v1/audit-logs", params={"entity_type": "USER"}, headers=admin_headers).json()
    assert data["total"] == 1
    entry = data["items"][0]
    assert entry["action"] == "CREATE" and entry["performed_by_name"] == admin_user.full_name
