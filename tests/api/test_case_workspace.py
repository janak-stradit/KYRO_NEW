"""
tests/api/test_case_workspace.py — The working parts of the case page:
requests for information, the case clock, screening decisions, counterparties,
the regulatory basis of a rule, and the draft narrative.
"""
import uuid
from datetime import date, timedelta

import pytest

from app.config import get_settings
from app.models.ai_interaction import AIInteraction
from app.models.alert import Alert
from app.models.audit import AuditLog
from app.models.customer import Customer, PEPSanctionsScreening
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.regulatory import RegulatorySection, RegulatorySource
from tests.api.conftest import _login, _make_user
from tests.api.test_alerts import _FP_RESOLUTION, _create_alert_via_sanctions_hit
from tests.api.test_patterns import Book, days_ago
from tests.api.test_screening_service import _make_entity, _make_source

pytestmark = pytest.mark.db

SOON = (date.today() + timedelta(days=7)).isoformat()


@pytest.fixture
def mock_ai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", True)


# ── Requests for information ─────────────────────────────────────────────

def test_request_for_information_lifecycle(client, auth_headers, analyst_user):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "rfi@example.com")
    url = f"/api/v1/alerts/{alert['id']}/requests"
    body = {"requested_from": "Relationship manager", "subject": "Contract behind the September wire", "due_date": SOON}

    assert client.post(url, json={**body, "due_date": (date.today() - timedelta(days=1)).isoformat()}, headers=auth_headers).status_code == 422
    assert client.post(url, json={**body, "subject": "   "}, headers=auth_headers).status_code == 422
    created = client.post(url, json=body, headers=auth_headers)
    assert created.status_code == 201, created.text
    request = created.json()
    assert request["status"] == "OPEN" and request["overdue"] is False and request["requested_by_name"] == analyst_user.full_name

    close = f"/api/v1/alerts/requests/{request['id']}"
    assert client.put(close, json={"status": "RECEIVED"}, headers=auth_headers).status_code == 422  # say what arrived
    received = client.put(close, json={"status": "RECEIVED", "response_note": "Signed contract received"}, headers=auth_headers)
    assert received.status_code == 200 and received.json()["status"] == "RECEIVED" and received.json()["closed_at"]
    assert client.put(close, json={"status": "CANCELLED"}, headers=auth_headers).status_code == 409

    assert [r["status"] for r in client.get(url, headers=auth_headers).json()] == ["RECEIVED"]
    kinds = [e["title"] for e in client.get(f"/api/v1/alerts/{alert['id']}/timeline", headers=auth_headers).json()["events"]]
    assert "Information requested from Relationship manager" in kinds and "Information received" in kinds


def test_overdue_request_and_closed_case(client, auth_headers, compliance_headers, db_session):
    from app.models.alert_request import AlertRequest

    alert = _create_alert_via_sanctions_hit(client, auth_headers, "rfi.overdue@example.com")
    url = f"/api/v1/alerts/{alert['id']}/requests"
    db_session.add(AlertRequest(alert_id=uuid.UUID(alert["id"]), requested_from="Customer", subject="Source of funds",
                                due_date=date.today() - timedelta(days=3)))
    db_session.commit()
    assert client.get(url, headers=auth_headers).json()[0]["overdue"] is True

    client.put(f"/api/v1/alerts/{alert['id']}/resolve", json=_FP_RESOLUTION, headers=compliance_headers)
    refused = client.post(url, json={"requested_from": "Customer", "subject": "More", "due_date": SOON}, headers=compliance_headers)
    assert refused.status_code == 409

    qa = _login(client, _make_user(db_session, username="qa.rfi", role="QA_REVIEWER").username)
    assert client.get(url, headers=qa).status_code == 200
    assert client.post(url, json={"requested_from": "Customer", "subject": "More", "due_date": SOON}, headers=qa).status_code == 403


# ── Case clock ───────────────────────────────────────────────────────────

def test_case_clock_measures_age_against_the_target(client, auth_headers, analyst_user, db_session):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "clock@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    settings = get_settings()
    row = db_session.get(Alert, uuid.UUID(alert["id"]))
    band = "high" if row.risk_score >= 80 else "medium" if row.risk_score >= 60 else "low"
    target = getattr(settings, f"case_target_days_{band}")

    clock = client.get(f"{url}/timeline", headers=auth_headers).json()["clock"]
    assert clock["age_days"] == 0 and clock["target_days"] == target and clock["overdue"] is False
    assert clock["risk_band"] == band and clock["assigned_at"] is None and clock["closed_at"] is None

    row.created_at = row.created_at - timedelta(days=target + 2)
    db_session.commit()
    client.put(f"{url}/assign", json={"assigned_to": str(analyst_user.id)}, headers=auth_headers)
    clock = client.get(f"{url}/timeline", headers=auth_headers).json()["clock"]
    assert clock["age_days"] == target + 2 and clock["overdue"] is True and clock["assigned_at"]


# ── Screening decisions ──────────────────────────────────────────────────

def _potential_match(db_session, **customer):
    source = _make_source(db_session)
    entity = _make_entity(db_session, source, aka_names=["V. Petrov"], programs=["UKRAINE-EO13661"], nationalities=["RU"])
    person = Customer(full_name="Vladimir Petrov", email="petrov@example.com", customer_type="INDIVIDUAL", country="LV", **customer)
    db_session.add(person)
    db_session.flush()
    screening = PEPSanctionsScreening(
        customer_id=person.id, watchlist_entity_id=entity.id, match_score=91, screening_type="SANCTIONS",
        match_status="POTENTIAL_MATCH", match_details={"matched_name": "Vladimir Petrov", "dob_match": False},
    )
    db_session.add(screening)
    db_session.commit()
    return person, screening


def test_screening_match_shows_the_list_entry_beside_the_customer(client, auth_headers, db_session):
    person, screening = _potential_match(db_session)
    matches = client.get(f"/api/v1/customers/{person.id}/screening-matches", headers=auth_headers).json()
    assert len(matches) == 1
    match = matches[0]
    assert match["id"] == str(screening.id) and match["match_score"] == 91.0 and match["resolution"] is None
    assert match["subject"] == {"kind": "Customer", "name": "Vladimir Petrov", "date_of_birth": None, "country": "LV"}
    listed = match["listed"]
    assert listed["name"] == "Vladimir Petrov" and listed["date_of_birth"] == "1970-01-01" and listed["list"] == "Test Source"
    assert listed["programs"] == ["UKRAINE-EO13661"] and listed["aka_names"] == ["V. Petrov"] and listed["still_listed"] is True


def test_clearing_a_match_records_who_and_why(client, auth_headers, analyst_user, db_session):
    person, screening = _potential_match(db_session)
    url = f"/api/v1/screening/{screening.id}/decision"
    assert client.put(url, json={"decision": "CLEARED", "notes": " "}, headers=auth_headers).status_code == 422
    cleared = client.put(url, json={"decision": "CLEARED", "notes": "Different date of birth and nationality"}, headers=auth_headers)
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()
    assert body["resolution"] == "CLEARED" and body["resolved_by_name"] == analyst_user.full_name
    assert body["resolution_notes"] == "Different date of birth and nationality" and body["match_status"] == "POTENTIAL_MATCH"
    db_session.refresh(person)
    assert person.sanctions_flag is False
    entry = db_session.query(AuditLog).filter_by(entity_type="CUSTOMER", entity_id=person.id, action="REVIEW").one()
    assert entry.new_values["resolution"] == "CLEARED" and entry.performed_by == analyst_user.id


def test_confirming_a_sanctions_match_flags_the_customer(client, auth_headers, db_session):
    person, screening = _potential_match(db_session)
    confirmed = client.put(f"/api/v1/screening/{screening.id}/decision", json={"decision": "CONFIRMED", "notes": "Same person"},
                           headers=auth_headers)
    assert confirmed.status_code == 200 and confirmed.json()["match_status"] == "CONFIRMED_MATCH"
    db_session.refresh(person)
    assert person.sanctions_flag is True and person.risk_level == "HIGH"

    l1 = _login(client, _make_user(db_session, username="l1.screen", role="L1_ANALYST").username)
    assert client.put(f"/api/v1/screening/{screening.id}/decision", json={"decision": "CLEARED", "notes": "x"}, headers=l1).status_code == 403
    assert client.put(f"/api/v1/screening/{uuid.uuid4()}/decision", json={"decision": "CLEARED", "notes": "x"},
                      headers=auth_headers).status_code == 404


# ── Counterparties ───────────────────────────────────────────────────────

def test_counterparties_are_ranked_and_new_ones_marked(client, auth_headers, db_session):
    book = Book(db_session, "Counterparty Case").steady_baseline(n=6, amount=100)
    book.txn(days_ago(4), amount=500, counterparty="New Trading Ltd", country="IR")
    book.txn(days_ago(3), amount=250, counterparty="New Trading Ltd", country="IR", currency="EUR")
    db_session.commit()

    data = client.get(f"/api/v1/customers/{book.customer.id}/counterparties", headers=auth_headers).json()
    assert data["transactions"] == 8 and data["counterparty_count"] == 2 and data["country_count"] == 2
    regular, fresh = data["counterparties"]
    assert regular["name"] == "Regular Payee" and regular["transactions"] == 6 and regular["new"] is False and regular["high_risk"] is False
    assert regular["totals"] == [{"currency": "USD", "amount": 600.0}]
    assert fresh["name"] == "New Trading Ltd" and fresh["new"] is True and fresh["high_risk"] is True
    assert fresh["totals"] == [{"currency": "USD", "amount": 500.0}, {"currency": "EUR", "amount": 250.0}]
    countries = {c["name"]: c for c in data["countries"]}
    assert countries["IR"]["new"] is True and countries["IR"]["high_risk"] is True and countries["GB"]["new"] is False


# ── Regulatory basis ─────────────────────────────────────────────────────

def test_regulatory_basis_lists_only_confirmed_mappings(client, auth_headers, db_session):
    source = RegulatorySource(code="TEST_BASIS", name="Test rule", source_kind="ECFR", config={"title": 99, "part": "1"})
    db_session.add(source)
    db_session.flush()
    section = RegulatorySection(source_id=source.id, section_ref="99 CFR 1.1", heading="Reporting", content="Report large transfers.",
                                version="2026-01-01", content_hash="x" * 64, is_current=True)
    db_session.add(section)
    db_session.flush()

    def obligation(action, status="CONFIRMED"):
        row = Obligation(section_id=section.id, section_ref=section.section_ref, section_version=section.version,
                         obligated_party="A dealer", action=action, category="REPORTING", status=status, extracted_by="mock")
        db_session.add(row)
        db_session.flush()
        return row

    confirmed = obligation("report each transfer above the threshold")
    db_session.add(ObligationMapping(obligation_id=confirmed.id, control_code="R001", status="CONFIRMED", proposed_by="user"))
    db_session.add(ObligationMapping(obligation_id=obligation("screen customers").id, control_code="R006", status="PROPOSED", proposed_by="mock"))
    db_session.add(ObligationMapping(obligation_id=obligation("old duty", status="SUPERSEDED").id, control_code="R001", status="CONFIRMED",
                                     proposed_by="user"))
    db_session.commit()

    basis = client.get("/api/v1/controls/basis", params={"codes": "R001, r006,R010"}, headers=auth_headers).json()
    assert set(basis) == {"R001", "R006", "R010"}
    assert [b["action"] for b in basis["R001"]] == ["report each transfer above the threshold"]
    assert basis["R001"][0]["citation"] == "99 CFR 1.1" and basis["R006"] == [] and basis["R010"] == []


# ── Draft narrative ──────────────────────────────────────────────────────

def test_draft_narrative_uses_only_the_facts_on_file(client, auth_headers, db_session, mock_ai):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "narrative@example.com")
    client.post(f"/api/v1/alerts/{alert['id']}/notes", json={"body": "Spoke to the relationship manager."}, headers=auth_headers)

    resp = client.post(f"/api/v1/alerts/{alert['id']}/draft-narrative", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True and body["provider"] == "mock"
    narrative = body["narrative"]
    for heading in ("Who", "What", "When", "Where", "Why it was flagged", "What was done"):
        assert heading in narrative
    assert "Risky Corp" in narrative and "R006" in narrative and "Spoke to the relationship manager." in narrative

    # The customer's name never reached the provider
    log = db_session.get(AIInteraction, uuid.UUID(body["interaction_id"]))
    assert log.prompt_id == "cases.draft_narrative" and "Risky Corp" not in log.input_redacted and "[PERSON_1]" in log.input_redacted
    assert log.entity_type == "ALERT" and str(log.entity_id) == alert["id"]


def test_draft_narrative_needs_ai_and_a_working_role(client, auth_headers, db_session, monkeypatch):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "narrative.off@example.com")
    monkeypatch.setattr(get_settings(), "kyro_ai_enabled", False)
    assert client.post(f"/api/v1/alerts/{alert['id']}/draft-narrative", headers=auth_headers).status_code == 409
    qa = _login(client, _make_user(db_session, username="qa.narrative", role="QA_REVIEWER").username)
    assert client.post(f"/api/v1/alerts/{alert['id']}/draft-narrative", headers=qa).status_code == 403


# ── Work queue: overdue and waiting on information ───────────────────────

def test_queue_marks_overdue_cases_and_open_requests(client, auth_headers, db_session):
    fresh = _create_alert_via_sanctions_hit(client, auth_headers, "queue.fresh@example.com")
    old = _create_alert_via_sanctions_hit(client, auth_headers, "queue.old@example.com")
    waiting = _create_alert_via_sanctions_hit(client, auth_headers, "queue.waiting@example.com")

    row = db_session.get(Alert, uuid.UUID(old["id"]))
    band = "high" if row.risk_score >= 80 else "medium" if row.risk_score >= 60 else "low"
    target = getattr(get_settings(), f"case_target_days_{band}")
    row.created_at = row.created_at - timedelta(days=target + 3)
    db_session.commit()
    client.post(f"/api/v1/alerts/{waiting['id']}/requests",
                json={"requested_from": "Customer", "subject": "Source of funds", "due_date": SOON}, headers=auth_headers)

    def queue(**params):
        return {a["id"]: a for a in client.get("/api/v1/alerts/queue", params=params, headers=auth_headers).json()["items"]}

    everything = queue()
    assert everything[old["id"]]["overdue"] is True and everything[old["id"]]["age_days"] == target + 3
    assert everything[fresh["id"]]["overdue"] is False and everything[fresh["id"]]["target_days"] == target
    assert everything[waiting["id"]]["open_requests"] == 1 and everything[waiting["id"]]["requests_overdue"] == 0
    assert everything[fresh["id"]]["open_requests"] == 0

    assert set(queue(attention="overdue")) == {old["id"]}
    assert set(queue(attention="awaiting_information")) == {waiting["id"]}
    summary = client.get("/api/v1/alerts/queue/summary", headers=auth_headers).json()
    assert summary["overdue"] == 1 and summary["awaiting_information"] == 1 and summary["target_days"][band] == target
    assert client.get("/api/v1/alerts/queue", params={"attention": "nonsense"}, headers=auth_headers).status_code == 422


# ── Case summary ─────────────────────────────────────────────────────────

def test_case_summary_is_written_once_and_kept_on_the_alert(client, auth_headers, db_session, mock_ai):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "summary@example.com")
    url = f"/api/v1/alerts/{alert['id']}"
    assert client.get(url, headers=auth_headers).json()["summary"] is None

    resp = client.post(f"{url}/summary", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock"] is True and body["summary_provider"] == "mock" and body["summary_at"]
    assert "Risky Corp" in body["summary"] and "R006" in body["summary"]
    assert "Nothing has been recorded on the case yet." in body["summary"]
    assert body["summary"].count(". ") <= 5  # a few sentences, not the whole file

    stored = client.get(url, headers=auth_headers).json()
    assert stored["summary"] == body["summary"] and stored["summary_provider"] == "mock"

    # A note changes what a regenerated summary says
    client.post(f"{url}/notes", json={"body": "Checked the invoices."}, headers=auth_headers)
    again = client.post(f"{url}/summary", headers=auth_headers).json()
    assert "1 action recorded on the case so far." in again["summary"]

    log = db_session.query(AIInteraction).filter_by(prompt_id="cases.summary").first()
    assert "Risky Corp" not in log.input_redacted


def test_case_summary_needs_ai_and_a_working_role(client, auth_headers, db_session, monkeypatch):
    alert = _create_alert_via_sanctions_hit(client, auth_headers, "summary.off@example.com")
    url = f"/api/v1/alerts/{alert['id']}/summary"
    qa = _login(client, _make_user(db_session, username="qa.summary", role="QA_REVIEWER").username)
    assert client.post(url, headers=qa).status_code == 403
    monkeypatch.setattr(get_settings(), "kyro_ai_enabled", False)
    assert client.post(url, headers=auth_headers).status_code == 409
    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=auth_headers).json()["summary"] is None
