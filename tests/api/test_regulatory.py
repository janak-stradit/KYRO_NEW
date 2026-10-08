"""
tests/api/test_regulatory.py — Regulatory knowledge base (Phase 11.3): eCFR
parsing, versioned ingestion, and cited Q&A. No test calls ecfr.gov or an AI
provider; the fixture below uses eCFR's XML layout with invented rule text.
"""
from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.models.ai_interaction import AIInteraction
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.regulatory import RegulatorySection, RegulatorySource
from app.services import ecfr_adapter, regulatory_ingestion_service
from app.services.ecfr_adapter import parse_sections
from app.services.regulatory_ingestion_service import ingest_source

pytestmark = pytest.mark.db


def _xml(widget_limit: str = "$7,500", include_gadgets: bool = True) -> bytes:
    gadgets = """
    <DIV8 N="9999.20" TYPE="SECTION" hierarchy_metadata="{&quot;citation&quot;:&quot;99 CFR 9999.20&quot;}">
      <HEAD>&#xA7; 9999.20 Gadget recordkeeping.</HEAD>
      <P>(a) Each gadget dealer shall retain gadget ledgers for <I>five</I> years.</P>
      <CITA TYPE="N">[75 FR 1, Jan. 1, 2010]</CITA>
    </DIV8>""" if include_gadgets else ""
    return f"""<?xml version="1.0"?>
<DIV5 N="9999" TYPE="PART">
  <HEAD>PART 9999 - WIDGET RULES</HEAD>
  <DIV6 N="A" TYPE="SUBPART">
    <DIV8 N="9999.10" TYPE="SECTION" hierarchy_metadata="{{&quot;citation&quot;:&quot;99 CFR 9999.10&quot;}}">
      <HEAD>&#xA7; 9999.10 Widget transfer reports.</HEAD>
      <P>(a) <I>General.</I> A widget dealer shall report each widget transfer of more than {widget_limit}.</P>
      <P>(b) The report shall be filed within 15 calendar days.</P>
      <CITA TYPE="N">[75 FR 1, Jan. 1, 2010]</CITA>
    </DIV8>{gadgets}
    <DIV8 N="9999.30" TYPE="SECTION"><HEAD>&#xA7; 9999.30 [Reserved]</HEAD></DIV8>
  </DIV6>
</DIV5>""".encode()


@pytest.fixture
def source(db_session) -> RegulatorySource:
    src = RegulatorySource(
        code="TEST_99_9999", name="Test widget rules", source_kind="ECFR", config={"title": 99, "part": "9999"}
    )
    db_session.add(src)
    # Keep the test's corpus separate from anything already loaded in this database
    db_session.query(KnowledgeChunk).update({KnowledgeChunk.is_current: False}, synchronize_session=False)
    db_session.commit()
    return src


@pytest.fixture
def feed(monkeypatch):
    """Stands in for ecfr.gov; tests change `feed["xml"]` to simulate a rule change."""
    state = {"xml": _xml(), "as_of": "2026-10-01", "amended": {"9999.10": "2024-03-01"}}

    def fake_fetch(config):
        if state["xml"] is None:
            raise httpx.ConnectError("ecfr.gov unreachable")
        return state["as_of"], parse_sections(
            state["xml"], title=config["title"], as_of=state["as_of"], amended=state["amended"]
        )

    monkeypatch.setattr(ecfr_adapter, "fetch", fake_fetch)
    return state


# ── Parsing ──────────────────────────────────────────────────────────────

def test_parse_sections_extracts_text_citation_and_version():
    sections = parse_sections(_xml(), title=99, as_of="2026-10-01", amended={"9999.10": "2024-03-01"})
    assert [s.section_ref for s in sections] == ["99 CFR 9999.10", "99 CFR 9999.20"]  # reserved section skipped

    widget = sections[0]
    assert widget.heading == "Widget transfer reports."
    assert widget.content == (
        "(a) General. A widget dealer shall report each widget transfer of more than $7,500.\n\n"
        "(b) The report shall be filed within 15 calendar days."
    )
    assert widget.version == "2024-03-01" and sections[1].version == "2026-10-01"
    assert widget.url == "https://www.ecfr.gov/current/title-99/section-9999.10"
    assert widget.source_note == "[75 FR 1, Jan. 1, 2010]"


# ── Ingestion ────────────────────────────────────────────────────────────

def test_ingest_stores_sections_and_skips_when_unchanged(db_session, source, feed):
    run = ingest_source(db_session, source)
    assert (run.status, run.sections_seen, run.sections_added, run.as_of) == ("SUCCESS", 2, 2, "2026-10-01")
    assert db_session.query(RegulatorySection).filter_by(source_id=source.id, is_current=True).count() == 2

    again = ingest_source(db_session, source)
    assert (again.status, again.sections_added, again.sections_changed) == ("SKIPPED_UNCHANGED", 0, 0)


def test_changed_section_becomes_a_new_version_and_old_text_is_kept(db_session, source, feed):
    ingest_source(db_session, source)
    feed.update(xml=_xml(widget_limit="$10,000"), amended={"9999.10": "2026-09-15"})

    run = ingest_source(db_session, source)
    assert (run.status, run.sections_added, run.sections_changed, run.sections_removed) == ("SUCCESS", 0, 1, 0)

    versions = (
        db_session.query(RegulatorySection)
        .filter_by(source_id=source.id, section_ref="99 CFR 9999.10")
        .order_by(RegulatorySection.version)
        .all()
    )
    assert [(v.version, v.is_current) for v in versions] == [("2024-03-01", False), ("2026-09-15", True)]
    assert "$7,500" in versions[0].content and "$10,000" in versions[1].content
    assert versions[0].superseded_at is not None

    current = db_session.query(KnowledgeChunk).filter_by(source_ref="99 CFR 9999.10", is_current=True).all()
    assert [c.version for c in current] == ["2026-09-15"]


def test_removed_section_stops_being_current(db_session, source, feed):
    ingest_source(db_session, source)
    feed["xml"] = _xml(include_gadgets=False)

    run = ingest_source(db_session, source)
    assert run.sections_removed == 1
    gadget = db_session.query(RegulatorySection).filter_by(source_id=source.id, section_ref="99 CFR 9999.20").one()
    assert gadget.is_current is False
    assert db_session.query(KnowledgeChunk).filter_by(source_ref="99 CFR 9999.20", is_current=True).count() == 0


def test_failed_fetch_is_recorded_and_keeps_existing_text(db_session, source, feed):
    ingest_source(db_session, source)
    feed["xml"] = None

    run = ingest_source(db_session, source)
    assert run.status == "FAILED" and "unreachable" in run.error_message
    assert db_session.query(RegulatorySection).filter_by(source_id=source.id, is_current=True).count() == 2


# ── Q&A ──────────────────────────────────────────────────────────────────

@pytest.fixture
def live_ai(monkeypatch):
    """AI enabled against a fake provider whose reply each test sets."""
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", False)
    monkeypatch.setattr(settings, "kyro_llm_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings, "kyro_llm_api_key", SecretStr("sk-testkey12345678"))
    state = {"reply": "{}", "requests": []}

    def fake_post(url, headers, json, timeout):
        state["requests"].append(json)
        return httpx.Response(200, json={"model": "test-model", "choices": [{"message": {"content": state["reply"]}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    return state


def _ask(client, headers, question):
    resp = client.post("/api/v1/regulatory/ask", json={"question": question}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ask_without_ai_returns_source_passages(client, auth_headers, db_session, source, feed):
    ingest_source(db_session, source)
    body = _ask(client, auth_headers, "When must a widget transfer report be filed?")

    assert body["mode"] == "EXTRACTIVE" and body["answer"] is None
    assert body["citations"][0] == "99 CFR 9999.10"
    top = body["sources"][0]
    assert top["version"] == "2024-03-01" and top["url"].endswith("section-9999.10")
    assert "15 calendar days" in top["excerpt"]


def test_ask_outside_the_sources_says_not_found_without_calling_the_ai(client, auth_headers, db_session, source, feed, live_ai):
    ingest_source(db_session, source)
    body = _ask(client, auth_headers, "What is the capital gains treatment of cryptocurrency staking?")

    assert body["mode"] == "NOT_FOUND" and body["sources"] == [] and body["citations"] == []
    assert "Not found" in body["answer"]
    assert live_ai["requests"] == []


def test_ask_with_ai_returns_cited_answer_and_logs_it(client, auth_headers, db_session, source, feed, live_ai):
    ingest_source(db_session, source)
    live_ai["reply"] = (
        '{"found": true, "answer": "Transfers above $7,500 must be reported within 15 calendar days.", '
        '"citations": ["99 CFR 9999.10", "12 CFR 1.1"]}'
    )
    body = _ask(client, auth_headers, "When must a widget transfer report be filed?")

    assert body["mode"] == "GENERATED" and body["verified"] is True
    assert body["citations"] == ["99 CFR 9999.10"]  # the citation that was not retrieved is dropped
    assert any("Dropped citations" in w for w in body["warnings"])
    assert "99 CFR 9999.10" in live_ai["requests"][0]["messages"][-1]["content"]

    row = db_session.get(AIInteraction, body["interaction_id"])
    assert (row.feature, row.prompt_id, row.status) == ("regulatory_qa", "regulatory.answer", "SUCCESS")


def test_ai_answer_without_a_valid_citation_is_marked_unverified(client, auth_headers, db_session, source, feed, live_ai):
    ingest_source(db_session, source)
    live_ai["reply"] = '{"found": true, "answer": "Reports are due in 15 days.", "citations": ["12 CFR 1.1"]}'
    body = _ask(client, auth_headers, "When must a widget transfer report be filed?")

    assert body["mode"] == "GENERATED" and body["verified"] is False and body["citations"] == []
    assert any("Unverified" in w for w in body["warnings"])


def test_ai_saying_not_found_is_respected(client, auth_headers, db_session, source, feed, live_ai):
    ingest_source(db_session, source)
    live_ai["reply"] = '{"found": false, "answer": "", "citations": []}'
    body = _ask(client, auth_headers, "Do widget transfer reports need a notary?")
    assert body["mode"] == "NOT_FOUND" and "Not found" in body["answer"]


# ── Endpoints ────────────────────────────────────────────────────────────

def test_ingest_endpoint_requires_compliance_or_admin(client, auth_headers, compliance_headers, db_session, source, feed):
    params = {"source_id": str(source.id)}
    assert client.post("/api/v1/regulatory/ingest", params=params, headers=auth_headers).status_code == 403

    resp = client.post("/api/v1/regulatory/ingest", params=params, headers=compliance_headers)
    assert resp.status_code == 200
    assert [(r["status"], r["sections_added"]) for r in resp.json()] == [("SUCCESS", 2)]

    sections = client.get("/api/v1/regulatory/sections", params=params, headers=auth_headers).json()
    assert [s["section_ref"] for s in sections["items"]] == ["99 CFR 9999.10", "99 CFR 9999.20"]
    detail = client.get(f"/api/v1/regulatory/sections/{sections['items'][0]['id']}", headers=auth_headers).json()
    assert "widget transfer" in detail["content"]

    runs = client.get("/api/v1/regulatory/runs", params=params, headers=auth_headers).json()
    assert runs["total"] == 1
    assert any(s["code"] == "TEST_99_9999" for s in client.get("/api/v1/regulatory/sources", headers=auth_headers).json())


# ── Obligations register ─────────────────────────────────────────────────

@pytest.fixture
def mock_ai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", True)
    return settings


def _extract(client, headers, source):
    return client.post("/api/v1/regulatory/obligations/extract", params={"source_id": str(source.id)}, headers=headers)


def _obligations(client, headers, **params):
    return client.get("/api/v1/regulatory/obligations", params=params, headers=headers).json()["items"]


def test_extract_proposes_obligations_with_verified_quotes(client, auth_headers, compliance_headers, db_session, source, feed, mock_ai):
    ingest_source(db_session, source)
    assert _extract(client, auth_headers, source).status_code == 403

    resp = _extract(client, compliance_headers, source)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "sections_processed": 2, "sections_skipped": 0, "obligations_proposed": 3, "extracted_by": "mock",
    }

    items = _obligations(client, auth_headers, section_ref="99 CFR 9999.10")
    assert {o["status"] for o in items} == {"PROPOSED"} and all(o["quote_verified"] for o in items)
    report = next(o for o in items if "report each widget transfer" in o["action"])
    assert report["obligated_party"] == "A widget dealer" and report["category"] == "REPORTING"
    assert report["section_version"] == "2024-03-01" and "$7,500" in report["source_quote"]
    deadline = next(o for o in items if o["deadline"])
    assert deadline["deadline"] == "within 15 calendar days"

    # Sections that already have obligations are skipped on the next run
    assert _extract(client, compliance_headers, source).json()["sections_processed"] == 0


def test_extract_requires_ai_to_be_enabled(client, compliance_headers, db_session, source, feed):
    ingest_source(db_session, source)
    assert _extract(client, compliance_headers, source).status_code == 409


def test_quote_not_in_section_is_flagged_unverified(client, compliance_headers, db_session, source, feed, live_ai):
    ingest_source(db_session, source)
    live_ai["reply"] = (
        '{"obligations": [{"obligated_party": "Widget dealer", "action": "report transfers", "deadline": null, '
        '"condition": null, "category": "NOT_A_CATEGORY", "source_quote": "Dealers must report within 5 days."}]}'
    )
    section = db_session.query(RegulatorySection).filter_by(source_id=source.id, section_ref="99 CFR 9999.10").one()
    resp = client.post(
        "/api/v1/regulatory/obligations/extract", params={"section_id": str(section.id)}, headers=compliance_headers
    )
    assert resp.status_code == 200 and resp.json()["obligations_proposed"] == 1

    item = _obligations(client, compliance_headers, section_ref="99 CFR 9999.10")[0]
    assert item["quote_verified"] is False and item["category"] == "OTHER"
    assert item["extracted_by"] == "openai_compatible"
    summary = client.get("/api/v1/regulatory/obligations/summary", headers=compliance_headers).json()
    assert summary["unverified_quotes"] >= 1 and summary["by_status"]["PROPOSED"] >= 1


def test_review_confirms_with_edits_and_records_the_decision(client, auth_headers, compliance_headers, compliance_user, db_session, source, feed, mock_ai):
    ingest_source(db_session, source)
    _extract(client, compliance_headers, source)
    item = _obligations(client, compliance_headers, section_ref="99 CFR 9999.20")[0]
    url = f"/api/v1/regulatory/obligations/{item['id']}/review"

    assert client.put(url, json={"decision": "CONFIRMED"}, headers=auth_headers).status_code == 403
    assert client.put(url, json={"decision": "MAYBE"}, headers=compliance_headers).status_code == 422

    resp = client.put(
        url,
        json={"decision": "CONFIRMED", "obligated_party": "Gadget dealers", "category": "RECORDKEEPING", "notes": "ok"},
        headers=compliance_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["status"], body["obligated_party"], body["category"]) == ("CONFIRMED", "Gadget dealers", "RECORDKEEPING")
    assert body["reviewed_by"] == str(compliance_user.id) and body["reviewed_at"]

    from app.models.audit import AuditLog
    from app.models.obligation import Obligation

    obligation = db_session.get(Obligation, item["id"])
    interaction = db_session.get(AIInteraction, obligation.ai_interaction_id)
    assert (interaction.human_decision, interaction.decided_by) == ("EDITED", compliance_user.id)
    audit = db_session.query(AuditLog).filter_by(entity_type="OBLIGATION", entity_id=obligation.id).one()
    assert audit.action == "APPROVE" and audit.new_values["obligated_party"] == "Gadget dealers"

    # Re-extraction replaces open proposals but never a reviewed obligation
    client.post(
        "/api/v1/regulatory/obligations/extract",
        params={"source_id": str(source.id), "redo": "true"}, headers=compliance_headers,
    )
    gadget = _obligations(client, compliance_headers, section_ref="99 CFR 9999.20")
    assert [(o["status"], o["obligated_party"]) for o in gadget] == [("CONFIRMED", "Gadget dealers")]


def test_changed_section_supersedes_its_obligations(client, compliance_headers, db_session, source, feed, mock_ai):
    ingest_source(db_session, source)
    _extract(client, compliance_headers, source)
    feed.update(xml=_xml(widget_limit="$10,000"), amended={"9999.10": "2026-09-15"})
    ingest_source(db_session, source)

    widget = _obligations(client, compliance_headers, section_ref="99 CFR 9999.10")
    assert widget and {o["status"] for o in widget} == {"SUPERSEDED"}
    assert {o["status"] for o in _obligations(client, compliance_headers, section_ref="99 CFR 9999.20")} == {"PROPOSED"}
    review = client.put(
        f"/api/v1/regulatory/obligations/{widget[0]['id']}/review", json={"decision": "CONFIRMED"}, headers=compliance_headers
    )
    assert review.status_code == 409

    # Extracting again picks up the new version of the changed section only
    assert _extract(client, compliance_headers, source).json()["sections_processed"] == 1
    fresh = _obligations(client, compliance_headers, section_ref="99 CFR 9999.10", status_filter="PROPOSED")
    assert fresh and all(o["section_version"] == "2026-09-15" for o in fresh)
    assert any("$10,000" in o["source_quote"] for o in fresh)
