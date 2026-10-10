"""
tests/api/test_visibility.py — Which records a user may see: cases by
assignment, and SAR-filed cases by sensitivity.
"""
import uuid

import pytest

from app.models.account import Account
from app.models.alert import Alert
from app.models.document import Document
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _create_alert_via_sanctions_hit

pytestmark = pytest.mark.db

_SAR = {"outcome": "SAR_FILED", "reasons": ["SANCTIONS_EXPOSURE"], "resolution_notes": "Confirmed", "sar_reference": "SAR-9"}


def _user(client, db_session, role, name):
    user = _make_user(db_session, username=name, role=role)
    return _login(client, user.username), user


def _queue_ids(client, headers, **params):
    return {a["id"] for a in client.get("/api/v1/alerts/queue", params={"status_filter": "ALL", **params}, headers=headers).json()["items"]}


# ── By assignment ────────────────────────────────────────────────────────

def test_analysts_see_their_own_cases_and_the_unassigned_pool(client, auth_headers, db_session):
    lead, _ = _user(client, db_session, "TEAM_LEAD", "vis.lead")
    one, first = _user(client, db_session, "L1_ANALYST", "vis.l1a")
    two, _ = _user(client, db_session, "L1_ANALYST", "vis.l1b")
    mine = _create_alert_via_sanctions_hit(client, auth_headers, "vis.mine@example.com")
    pool = _create_alert_via_sanctions_hit(client, auth_headers, "vis.pool@example.com")
    assert client.put(f"/api/v1/alerts/{mine['id']}/assign", json={"assigned_to": str(first.id)}, headers=lead).status_code == 200

    assert {mine["id"], pool["id"]} <= _queue_ids(client, one)
    assert pool["id"] in _queue_ids(client, two) and mine["id"] not in _queue_ids(client, two)
    assert {mine["id"], pool["id"]} <= _queue_ids(client, lead)

    url = f"/api/v1/alerts/{mine['id']}"
    assert client.get(url, headers=one).status_code == 200
    for path in ("", "/timeline", "/requests"):
        assert client.get(url + path, headers=two).status_code == 404, path
    assert client.post(f"{url}/notes", json={"body": "Not my case"}, headers=two).status_code == 404
    assert client.put(f"{url}/escalate", json={"reasons": []}, headers=two).status_code == 404
    listed = {a["id"] for a in client.get("/api/v1/alerts", params={"page_size": 100}, headers=two).json()["items"]}
    assert mine["id"] not in listed and pool["id"] in listed

    # The headline numbers follow the same rule
    assert client.get("/api/v1/alerts/queue/summary", headers=two).json()["unresolved"] == 1
    assert client.get("/api/v1/alerts/queue/summary", headers=lead).json()["unresolved"] == 2
    recent = {a["id"] for a in client.get("/api/v1/dashboard/recent-alerts", headers=two).json()}
    assert mine["id"] not in recent and pool["id"] in recent


def test_customer_records_follow_the_cases_an_investigator_can_see(client, auth_headers, db_session):
    lead, _ = _user(client, db_session, "TEAM_LEAD", "cust.lead")
    investigator, me = _user(client, db_session, "L2_INVESTIGATOR", "cust.l2")
    other_headers, other = _user(client, db_session, "L2_INVESTIGATOR", "cust.l2b")
    kyc, _ = _user(client, db_session, "KYC_ANALYST", "cust.kyc")
    theirs = _create_alert_via_sanctions_hit(client, auth_headers, "cust.theirs@example.com")
    pool = _create_alert_via_sanctions_hit(client, auth_headers, "cust.pool@example.com")
    client.put(f"/api/v1/alerts/{theirs['id']}/assign", json={"assigned_to": str(other.id)}, headers=lead)
    hidden, shown = theirs["customer_id"], pool["customer_id"]
    account = db_session.query(Account).filter_by(customer_id=uuid.UUID(hidden)).first()

    for url in (
        f"/api/v1/customers/{hidden}", f"/api/v1/customers/{hidden}/risk-profile", f"/api/v1/customers/{hidden}/activity",
        f"/api/v1/customers/{hidden}/case-history", f"/api/v1/customers/{hidden}/counterparties",
        f"/api/v1/customers/{hidden}/screening-matches", f"/api/v1/customers/{hidden}/beneficial-owners",
        f"/api/v1/transactions?customer_id={hidden}", f"/api/v1/accounts?customer_id={hidden}", f"/api/v1/accounts/{account.id}",
        f"/api/v1/documents?customer_id={hidden}", f"/api/v1/kyc-reviews?customer_id={hidden}",
    ):
        assert client.get(url, headers=investigator).status_code == 404, url
        assert client.get(url, headers=other_headers).status_code == 200, url

    assert client.get(f"/api/v1/customers/{shown}", headers=investigator).status_code == 200
    assert client.get(f"/api/v1/transactions?customer_id={shown}", headers=investigator).status_code == 200
    # A whole collection is not listed for a role limited to its cases
    for url in ("/api/v1/transactions", "/api/v1/accounts", "/api/v1/kyc-reviews"):
        assert client.get(url, headers=investigator).status_code == 403, url
        assert client.get(url, headers=lead).status_code == 200, url
    # KYC analysts work across all customers
    assert client.get(f"/api/v1/customers/{hidden}", headers=kyc).status_code == 200
    assert client.get("/api/v1/kyc-reviews", headers=kyc).status_code == 200


# ── By sensitivity ───────────────────────────────────────────────────────

def test_sar_filed_cases_are_seen_only_by_mlro_admin_and_auditor(client, auth_headers, admin_headers, db_session):
    mlro, _ = _user(client, db_session, "MLRO", "sar.mlro")
    lead, _ = _user(client, db_session, "TEAM_LEAD", "sar.lead")
    qa, _ = _user(client, db_session, "QA_REVIEWER", "sar.qa")
    auditor, _ = _user(client, db_session, "AUDITOR", "sar.auditor")
    filed = _create_alert_via_sanctions_hit(client, auth_headers, "sar.filed@example.com")
    customer_id = uuid.UUID(filed["customer_id"])
    other = Alert(customer_id=customer_id, risk_score=70, triggered_rules={"rules": ["R006"]}, status="OPEN")
    db_session.add(other)
    db_session.commit()
    url = f"/api/v1/alerts/{filed['id']}"
    assert client.put(f"{url}/resolve", json=_SAR, headers=mlro).status_code == 200

    for headers in (mlro, admin_headers, auditor):
        assert client.get(url, headers=headers).status_code == 200
        assert filed["id"] in _queue_ids(client, headers)
    for headers in (lead, qa, auth_headers):
        assert client.get(url, headers=headers).status_code == 404
        assert client.get(f"{url}/timeline", headers=headers).status_code == 404
        assert filed["id"] not in _queue_ids(client, headers)
        assert filed["id"] not in _queue_ids(client, headers, status_filter="RESOLVED")
    assert client.put(f"{url}/qa", json={"result": "PASS"}, headers=qa).status_code == 404

    # Nothing about the customer's other case gives the filing away
    history = lambda headers: client.get(
        f"/api/v1/customers/{customer_id}/case-history", params={"alert_id": str(other.id)}, headers=headers).json()
    seen, unseen = history(mlro), history(lead)
    assert seen["outcomes"] == {"SAR_FILED": 1} and seen["same_rules"][0]["sar_filed"] == 1 and seen["resolved"] == 1
    assert unseen["outcomes"] == {} and unseen["same_rules"][0]["sar_filed"] == 0 and unseen["total"] == 0

    factors = lambda headers: [f["risk_factor"] for f in client.get(f"/api/v1/customers/{customer_id}/risk-profile", headers=headers).json()]
    assert any("SAR" in f for f in factors(mlro)) and not any("SAR" in f for f in factors(lead))


def test_documents_on_a_sar_case_follow_the_case(client, auth_headers, db_session):
    mlro, _ = _user(client, db_session, "MLRO", "doc.mlro")
    lead, _ = _user(client, db_session, "TEAM_LEAD", "doc.lead")
    filed = _create_alert_via_sanctions_hit(client, auth_headers, "doc.sar@example.com")
    customer_id = uuid.UUID(filed["customer_id"])

    def document(alert_id, name):
        row = Document(customer_id=customer_id, alert_id=alert_id, doc_type="ID_DOCUMENT", filename=name, content_type="text/plain",
                       size_bytes=1, sha256=uuid.uuid4().hex * 2, storage_key=name, page_count=1, text_status="EXTRACTED")
        db_session.add(row)
        db_session.commit()
        return row

    on_case, general = document(uuid.UUID(filed["id"]), "sar-evidence.txt"), document(None, "passport.txt")
    names = lambda headers: {d["filename"] for d in client.get(f"/api/v1/documents?customer_id={customer_id}", headers=headers).json()}
    assert names(lead) == {"sar-evidence.txt", "passport.txt"}  # nothing filed yet

    assert client.put(f"/api/v1/alerts/{filed['id']}/resolve", json=_SAR, headers=mlro).status_code == 200
    assert names(mlro) == {"sar-evidence.txt", "passport.txt"}
    assert names(lead) == {"passport.txt"}
    assert client.get(f"/api/v1/documents/{on_case.id}", headers=lead).status_code == 404
    assert client.get(f"/api/v1/documents/{on_case.id}", headers=mlro).status_code == 200
    assert client.get(f"/api/v1/documents/{general.id}", headers=lead).status_code == 200


# ── Dashboard: my cases, by role ─────────────────────────────────────────

def test_dashboard_my_work_is_shaped_by_role(client, auth_headers, db_session):
    lead, lead_user = _user(client, db_session, "TEAM_LEAD", "work.lead")
    mlro, _ = _user(client, db_session, "MLRO", "work.mlro")
    qa, _ = _user(client, db_session, "QA_REVIEWER", "work.qa")
    one, first = _user(client, db_session, "L1_ANALYST", "work.l1a")
    two, _ = _user(client, db_session, "L1_ANALYST", "work.l1b")
    viewer, _ = _user(client, db_session, "EXECUTIVE_VIEWER", "work.exec")
    mine = _create_alert_via_sanctions_hit(client, auth_headers, "work.mine@example.com")
    pool = _create_alert_via_sanctions_hit(client, auth_headers, "work.pool@example.com")
    escalated = _create_alert_via_sanctions_hit(client, auth_headers, "work.esc@example.com")
    client.put(f"/api/v1/alerts/{mine['id']}/assign", json={"assigned_to": str(first.id)}, headers=lead)
    client.put(f"/api/v1/alerts/{escalated['id']}/escalate", json={"reasons": ["SANCTIONS_EXPOSURE"]}, headers=lead)
    work = lambda headers: client.get("/api/v1/dashboard/my-work", headers=headers).json()

    # The analyst who owns a case sees it; a colleague does not
    own = work(one)
    assert own["role_label"] == "Level 1 Analyst" and own["sees_all_cases"] is False
    assert own["assigned_to_me"]["count"] == 1 and [c["id"] for c in own["assigned_to_me"]["items"]] == [mine["id"]]
    assert own["assigned_to_me"]["items"][0]["customer_name"] == "Risky Corp" and own["unassigned"] == 2
    assert "team" not in own and "escalated" not in own and "awaiting_quality_check" not in own
    assert work(two)["assigned_to_me"]["count"] == 0 and work(two)["unassigned"] == 2

    # A team lead sees who holds what
    team = work(lead)
    assert team["sees_all_cases"] is True and team["assigned_to_me"]["count"] == 0
    assert [(m["name"], m["open"], m["overdue"]) for m in team["team"]] == [(first.full_name, 1, 0)]
    assert team["team"][0]["role_label"] == "Level 1 Analyst" and "escalated" not in team

    # The MLRO also sees what is waiting for a decision; QA sees what is waiting for a check
    decision = work(mlro)
    assert decision["escalated"]["count"] == 1 and decision["escalated"]["items"][0]["id"] == escalated["id"]
    assert decision["awaiting_quality_check"] == 0 and work(qa)["awaiting_quality_check"] == 0
    client.put(f"/api/v1/alerts/{pool['id']}/resolve",
               json={"outcome": "FALSE_POSITIVE", "reasons": ["DUPLICATE_ALERT"], "resolution_notes": "Duplicate"}, headers=mlro)
    assert work(qa)["awaiting_quality_check"] == 1
    assert work(mlro)["awaiting_quality_check"] == 0  # not the cases they resolved themselves

    assert client.get("/api/v1/dashboard/my-work", headers=viewer).status_code == 403


def test_cases_are_assigned_only_to_people_who_work_them(client, auth_headers, db_session):
    lead, _ = _user(client, db_session, "TEAM_LEAD", "own.lead")
    _, analyst = _user(client, db_session, "L1_ANALYST", "own.l1")
    _, auditor = _user(client, db_session, "AUDITOR", "own.auditor")
    _, viewer = _user(client, db_session, "EXECUTIVE_VIEWER", "own.exec")
    _, qa = _user(client, db_session, "QA_REVIEWER", "own.qa")
    _, gone = _user(client, db_session, "L1_ANALYST", "own.gone")
    gone.is_active = False
    db_session.commit()
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "own.case@example.com")
    url = f"/api/v1/alerts/{alert['id']}/assign"

    offered = {a["id"] for a in client.get("/api/v1/alerts/assignees", headers=lead).json()}
    assert str(analyst.id) in offered
    assert not offered & {str(auditor.id), str(viewer.id), str(qa.id), str(gone.id)}

    for person in (auditor, viewer, qa, gone):
        assert client.put(url, json={"assigned_to": str(person.id)}, headers=lead).status_code == 422, person.username
    assert client.put(url, json={"assigned_to": str(uuid.uuid4())}, headers=lead).status_code == 422
    assert client.put(url, json={"assigned_to": str(analyst.id)}, headers=lead).status_code == 200


def test_header_search_finds_customers_the_user_may_see(client, auth_headers, db_session):
    lead, _ = _user(client, db_session, "TEAM_LEAD", "find.lead")
    mine_headers, _ = _user(client, db_session, "L2_INVESTIGATOR", "find.l2")
    _, other = _user(client, db_session, "L2_INVESTIGATOR", "find.l2b")
    viewer, _ = _user(client, db_session, "EXECUTIVE_VIEWER", "find.exec")
    pool = _create_alert_via_sanctions_hit(client, auth_headers, "find.pool@example.com")
    taken = _create_alert_via_sanctions_hit(client, auth_headers, "find.taken@example.com")
    client.put(f"/api/v1/alerts/{taken['id']}/assign", json={"assigned_to": str(other.id)}, headers=lead)
    find = lambda headers, **params: client.get("/api/v1/search", params=params, headers=headers)

    everyone = find(lead, q="risky").json()
    assert {r["customer_id"] for r in everyone} == {pool["customer_id"], taken["customer_id"]}
    row = next(r for r in everyone if r["customer_id"] == pool["customer_id"])
    assert row["name"] == "Risky Corp" and row["open_alerts"] == 1 and row["top_alert_id"] == pool["id"] and row["sanctions"] is True

    assert {r["customer_id"] for r in find(mine_headers, q="RISKY").json()} == {pool["customer_id"]}  # not the colleague's case
    assert find(mine_headers, customer_id=taken["customer_id"]).json() == []
    assert [r["customer_id"] for r in find(lead, customer_id=taken["customer_id"]).json()] == [taken["customer_id"]]
    assert find(lead, q="r").json() == [] and find(lead, q="no such customer").json() == []
    assert find(viewer, q="risky").status_code == 403


def test_several_alerts_are_assigned_in_one_step(client, auth_headers, db_session):
    lead, _ = _user(client, db_session, "TEAM_LEAD", "bulk.lead")
    l1, analyst = _user(client, db_session, "L1_ANALYST", "bulk.l1")
    _, auditor = _user(client, db_session, "AUDITOR", "bulk.auditor")
    first = _create_alert_via_sanctions_hit(client, auth_headers, "bulk.one@example.com")
    second = _create_alert_via_sanctions_hit(client, auth_headers, "bulk.two@example.com")
    customer_id = uuid.UUID(first["customer_id"])
    extra = Alert(customer_id=customer_id, risk_score=70, triggered_rules={"rules": ["R006"]}, status="ESCALATED")
    closed = Alert(customer_id=customer_id, risk_score=70, triggered_rules={"rules": ["R006"]}, status="RESOLVED")
    db_session.add_all([extra, closed])
    db_session.commit()
    url = "/api/v1/alerts/bulk-assign"

    assert client.put(url, json={"assigned_to": str(analyst.id), "customer_id": str(customer_id)}, headers=l1).status_code == 403
    assert client.put(url, json={"assigned_to": str(auditor.id), "customer_id": str(customer_id)}, headers=lead).status_code == 422
    assert client.put(url, json={"assigned_to": str(analyst.id)}, headers=lead).status_code == 422  # nothing to assign
    assert client.put(url, json={"assigned_to": str(analyst.id), "customer_id": str(customer_id), "alert_ids": [first["id"]]},
                      headers=lead).status_code == 422

    whole = client.put(url, json={"assigned_to": str(analyst.id), "customer_id": str(customer_id)}, headers=lead)
    assert whole.status_code == 200, whole.text
    assert whole.json() == {"assigned": 2, "already_with_owner": 0, "skipped": 0, "assigned_to_name": analyst.full_name}
    db_session.expire_all()
    assert db_session.get(Alert, uuid.UUID(first["id"])).status == "ASSIGNED"
    assert db_session.get(Alert, extra.id).status == "ESCALATED" and db_session.get(Alert, extra.id).assigned_to == analyst.id
    assert db_session.get(Alert, closed.id).assigned_to is None  # resolved alerts are left alone

    picked = client.put(url, json={"assigned_to": str(analyst.id), "alert_ids": [first["id"], second["id"], str(closed.id), str(uuid.uuid4())]},
                        headers=lead)
    assert picked.json() == {"assigned": 1, "already_with_owner": 1, "skipped": 2, "assigned_to_name": analyst.full_name}
    assert client.put(f"/api/v1/alerts/{closed.id}/assign", json={"assigned_to": str(analyst.id)}, headers=lead).status_code == 409
