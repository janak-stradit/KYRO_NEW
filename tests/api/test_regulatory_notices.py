"""
tests/api/test_regulatory_notices.py — Federal Register notices for loaded CFR
parts (Phase 11.5). No test calls federalregister.gov.
"""
from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.models.regulatory import RegulatorySource
from app.models.regulatory_notice import RegulatoryNotice
from app.services import federal_register_service

pytestmark = pytest.mark.db

RECENT = (date.today() - timedelta(days=10)).isoformat()
FUTURE = (date.today() + timedelta(days=60)).isoformat()


def _notice(number, title, kind="Proposed Rule", **extra):
    return {
        "document_number": number, "title": title, "type": kind, "action": "Notice of proposed rulemaking.",
        "abstract": "Summary of " + title, "publication_date": RECENT, "effective_on": None, "comments_close_on": FUTURE,
        "html_url": f"https://www.federalregister.gov/d/{number}",
        "agencies": [{"name": "Financial Crimes Enforcement Network"}, {"raw_name": "TREASURY"}],
        **extra,
    }


@pytest.fixture
def sources(db_session):
    """Two test parts under one title, plus a disabled source that must be ignored."""
    db_session.query(RegulatorySource).update({RegulatorySource.is_enabled: False}, synchronize_session=False)
    db_session.add_all([
        RegulatorySource(code="NT_98_100", name="Test part 100", source_kind="ECFR", config={"title": 98, "part": "100"}),
        RegulatorySource(code="NT_98_200", name="Test part 200", source_kind="ECFR", config={"title": 98, "part": "200"}),
        RegulatorySource(code="NT_98_300", name="Disabled", source_kind="ECFR", config={"title": 98, "part": "300"}, is_enabled=False),
    ])
    db_session.commit()


@pytest.fixture
def feed(monkeypatch):
    state = {"calls": [], "by_part": {
        "100": [_notice("NT-0001", "Widget reporting threshold"), _notice("NT-0002", "Widget final rule", kind="Rule", effective_on=FUTURE)],
        "200": [_notice("NT-0001", "Widget reporting threshold")],  # the same notice amends both parts
    }}

    def fake_fetch(title, part, since):
        state["calls"].append((title, part))
        if state["by_part"].get(part) is None:
            raise httpx.ConnectError("unreachable")
        return state["by_part"][part]

    monkeypatch.setattr(federal_register_service, "fetch_part", fake_fetch)
    return state


def _mine(client, headers):
    return [n for n in client.get("/api/v1/changes/notices", headers=headers).json() if n["document_number"].startswith("NT-")]


def test_sync_stores_notices_once_with_the_parts_they_amend(client, auth_headers, compliance_headers, sources, feed):
    assert client.post("/api/v1/changes/notices/sync", headers=auth_headers).status_code == 403

    resp = client.post("/api/v1/changes/notices/sync", headers=compliance_headers)
    assert resp.status_code == 200
    assert resp.json() == {"parts_checked": 2, "notices_found": 2, "notices_added": 2, "failed": []}
    assert feed["calls"] == [(98, "100"), (98, "200")]  # the disabled source is not checked

    notices = {n["document_number"]: n for n in _mine(client, auth_headers)}
    shared = notices["NT-0001"]
    assert shared["matched_parts"] == ["98 CFR Part 100", "98 CFR Part 200"]
    assert (shared["notice_type"], shared["status"], shared["comments_close_on"]) == ("Proposed Rule", "NEW", FUTURE)
    assert shared["agencies"] == ["Financial Crimes Enforcement Network", "TREASURY"]
    assert notices["NT-0002"]["effective_on"] == FUTURE

    # Syncing again adds nothing
    assert client.post("/api/v1/changes/notices/sync", headers=compliance_headers).json()["notices_added"] == 0
    assert len(_mine(client, auth_headers)) == 2


def test_assessment_survives_a_resync_and_details_are_refreshed(client, auth_headers, compliance_headers, sources, feed, db_session):
    client.post("/api/v1/changes/notices/sync", headers=compliance_headers)
    notice = next(n for n in _mine(client, auth_headers) if n["document_number"] == "NT-0001")
    url = f"/api/v1/changes/notices/{notice['id']}/assess"

    assert client.put(url, json={"status": "NO_ACTION"}, headers=auth_headers).status_code == 403
    assert client.put(url, json={"status": "MAYBE"}, headers=compliance_headers).status_code == 422
    assessed = client.put(url, json={"status": "ACTION_REQUIRED", "notes": "Threshold may change"}, headers=compliance_headers)
    assert assessed.status_code == 200 and assessed.json()["status"] == "ACTION_REQUIRED"

    feed["by_part"]["100"][0] = _notice("NT-0001", "Widget reporting threshold", effective_on=FUTURE)  # date added later
    client.post("/api/v1/changes/notices/sync", headers=compliance_headers)
    refreshed = next(n for n in _mine(client, auth_headers) if n["document_number"] == "NT-0001")
    assert (refreshed["status"], refreshed["assessment_notes"], refreshed["effective_on"]) == ("ACTION_REQUIRED", "Threshold may change", FUTURE)
    assert [n["document_number"] for n in client.get("/api/v1/changes/notices", params={"status_filter": "ACTION_REQUIRED"}, headers=auth_headers).json() if n["document_number"].startswith("NT-")] == ["NT-0001"]


def test_one_unreachable_part_does_not_block_the_others(client, compliance_headers, sources, feed, db_session):
    feed["by_part"]["200"] = None
    body = client.post("/api/v1/changes/notices/sync", headers=compliance_headers).json()
    assert body["notices_added"] == 2 and body["failed"] == ["98 CFR Part 200: ConnectError"]
    assert db_session.query(RegulatoryNotice).filter(RegulatoryNotice.document_number.like("NT-%")).count() == 2
