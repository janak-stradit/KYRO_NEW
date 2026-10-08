"""
tests/api/test_documents.py — Document review copilot (Phase 11.1): upload,
text extraction, AI field extraction (mock), checks against KYRO's records
and analyst review. Files are written to a temporary directory.
"""
from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta

import httpx
import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.models.audit import AuditLog
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer
from app.models.document import Document

pytestmark = pytest.mark.db

EXPIRED = (date.today() - timedelta(days=30)).isoformat()
VALID = (date.today() + timedelta(days=900)).isoformat()


def make_pdf(pages: list[list[str]]) -> bytes:
    """A small, valid, text-based PDF with one list of lines per page."""
    objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        text = b"BT /F1 12 Tf 72 720 Td 16 TL " + b" ".join(
            b"(" + line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)").encode("latin-1") + b") Tj T*" for line in lines
        ) + b" ET"
        objects.append(b"<< /Length %d >>\nstream\n" % len(text) + text + b"\nendstream")
        content = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content
        )
        kids.append(len(objects))
    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "document_storage_dir", str(tmp_path / "documents"))
    return tmp_path / "documents"


@pytest.fixture
def mock_ai(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", True)


@pytest.fixture
def customer(db_session) -> Customer:
    c = Customer(
        full_name="Jane Alexandra Doe", email="jane.doe.docs@example.com", customer_type="INDIVIDUAL",
        date_of_birth=date(1985, 3, 14), country="GB",
    )
    db_session.add(c)
    db_session.commit()
    return c


def _upload(client, headers, customer, data, *, doc_type="ID_DOCUMENT", filename="passport.pdf", **extra):
    return client.post(
        "/api/v1/documents",
        data={"customer_id": str(customer.id), "doc_type": doc_type, **extra},
        files={"file": (filename, data, "application/octet-stream")},
        headers=headers,
    )


PASSPORT = [
    ["PASSPORT", "Name: Jane Alexandra Doe", "Date of birth: 14/03/1985", "Nationality: FR"],
    ["Passport number: X1234567", f"Date of expiry: {EXPIRED}"],
]


# ── Upload and text ──────────────────────────────────────────────────────

def test_upload_pdf_stores_file_and_reads_pages(client, auth_headers, customer, storage, db_session):
    resp = _upload(client, auth_headers, customer, make_pdf(PASSPORT), filename="../../evil name.pdf")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["content_type"], body["page_count"], body["text_status"]) == ("application/pdf", 2, "EXTRACTED")
    assert body["filename"] == "evil name.pdf" and len(body["sha256"]) == 64 and body["retention_until"]

    stored = list(storage.iterdir())
    assert len(stored) == 1 and stored[0].name != "evil name.pdf"  # stored under a generated name
    detail = client.get(f"/api/v1/documents/{body['id']}", headers=auth_headers).json()
    assert "Jane Alexandra Doe" in detail["pages"][0]["text"] and "X1234567" in detail["pages"][1]["text"]
    assert detail["extractions"] == []

    download = client.get(f"/api/v1/documents/{body['id']}/file", headers=auth_headers)
    assert download.status_code == 200 and download.content.startswith(b"%PDF-")
    assert db_session.query(AuditLog).filter_by(entity_type="DOCUMENT", action="CREATE").count() >= 1
    assert client.get("/api/v1/documents", params={"customer_id": str(customer.id)}, headers=auth_headers).json()[0]["id"] == body["id"]


def test_word_and_text_files_are_read(client, auth_headers, customer):
    docx = _upload(client, auth_headers, customer, make_docx(["Name: Jane Alexandra Doe", "Address: 1 High Street"]), filename="letter.docx", doc_type="PROOF_OF_ADDRESS")
    assert docx.status_code == 201 and docx.json()["text_status"] == "EXTRACTED"
    text = _upload(client, auth_headers, customer, b"Name: Jane Alexandra Doe\n", filename="note.txt", doc_type="OTHER")
    assert text.status_code == 201 and text.json()["content_type"] == "text/plain"


def test_rejects_other_file_types_and_bad_requests(client, auth_headers, customer):
    assert _upload(client, auth_headers, customer, b"MZ\x90\x00\x03\x00\x00\x00binary", filename="invoice.pdf").status_code == 415
    assert _upload(client, auth_headers, customer, b"", filename="empty.pdf").status_code == 422
    assert _upload(client, auth_headers, customer, make_pdf(PASSPORT), doc_type="SELFIE").status_code == 422
    assert client.post("/api/v1/documents", data={"customer_id": str(customer.id), "doc_type": "OTHER"}, files={"file": ("a.txt", b"x")}).status_code == 401


def test_scanned_pdf_needs_ocr_and_cannot_be_extracted(client, auth_headers, customer, mock_ai):
    resp = _upload(client, auth_headers, customer, make_pdf([[]]))
    assert resp.status_code == 201 and resp.json()["text_status"] == "NEEDS_OCR"
    extract = client.post(f"/api/v1/documents/{resp.json()['id']}/extract", headers=auth_headers)
    assert extract.status_code == 422 and "OCR" in extract.json()["detail"]


# ── Extraction and checks ────────────────────────────────────────────────

def _extract(client, headers, customer, pages=PASSPORT, **kwargs):
    document = _upload(client, headers, customer, make_pdf(pages), **kwargs).json()
    resp = client.post(f"/api/v1/documents/{document['id']}/extract", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_extraction_cites_pages_and_checks_against_the_record(client, auth_headers, customer, mock_ai):
    detail = _extract(client, auth_headers, customer)
    fields = {e["field"]: e for e in detail["extractions"]}
    assert set(fields) == {"full_name", "date_of_birth", "nationality", "id_number", "expiry_date"}
    assert all(e["quote_verified"] and e["status"] == "PROPOSED" and e["extracted_by"] == "mock" for e in fields.values())

    assert (fields["full_name"]["check_status"], fields["full_name"]["page_number"]) == ("MATCH", 1)
    assert (fields["date_of_birth"]["value"], fields["date_of_birth"]["check_status"]) == ("14/03/1985", "MATCH")
    assert (fields["nationality"]["check_status"], fields["nationality"]["record_value"]) == ("MISMATCH", "GB")
    assert (fields["id_number"]["check_status"], fields["id_number"]["page_number"]) == ("NOT_CHECKED", 2)
    assert fields["expiry_date"]["check_status"] == "EXPIRED" and EXPIRED in fields["expiry_date"]["check_detail"]
    assert detail["summary"] == {"fields": 5, "awaiting_review": 5, "issues": 2, "unverified": 0}
    assert detail["extracted_by"] == "mock"


def test_name_mismatch_and_valid_expiry(client, auth_headers, customer, mock_ai):
    detail = _extract(client, auth_headers, customer, pages=[["Name: John Smith", f"Date of expiry: {VALID}"]])
    fields = {e["field"]: e for e in detail["extractions"]}
    assert (fields["full_name"]["check_status"], fields["full_name"]["record_value"]) == ("MISMATCH", "Jane Alexandra Doe")
    assert fields["expiry_date"]["check_status"] == "MATCH"


def test_company_registry_checks_owners_against_the_ubo_register(client, auth_headers, db_session, mock_ai):
    company = Customer(full_name="Northwind Trading Ltd", email="northwind.docs@example.com", customer_type="CORPORATE")
    db_session.add(company)
    db_session.flush()
    db_session.add(BeneficialOwner(customer_id=company.id, full_name="Priya Raman", ownership_percentage=40))
    db_session.commit()

    detail = _extract(
        client, auth_headers, company, doc_type="COMPANY_REGISTRY", filename="registry.pdf",
        pages=[["Company name: Northwind Trading Limited", "Registration number: 88213377", "Director: Omar Haddad",
                "Beneficial owner: Priya Raman (40%)", "Beneficial owner: Viktor Antonov (35%)"]],
    )
    owners = {e["value"]: e for e in detail["extractions"] if e["field"] == "beneficial_owner"}
    assert owners["Priya Raman (40%)"]["check_status"] == "MATCH"
    missing = owners["Viktor Antonov (35%)"]
    assert (missing["check_status"], missing["check_detail"]) == ("NOT_ON_RECORD", "Not in the beneficial ownership register")
    assert {e["field"] for e in detail["extractions"]} >= {"company_name", "registration_number", "director"}


def test_value_the_model_made_up_is_flagged_unverified(client, auth_headers, customer, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "kyro_ai_enabled", True)
    monkeypatch.setattr(settings, "kyro_llm_mock", False)
    monkeypatch.setattr(settings, "kyro_llm_base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings, "kyro_llm_api_key", SecretStr("sk-testkey12345678"))
    reply = ('{"fields": [{"field": "id_number", "value": "Z9999999", "page": 2, "source_quote": "Passport number: Z9999999", "confidence": 0.9},'
             ' {"field": "favourite_colour", "value": "blue", "page": 1}]}')
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent["prompt"] = json["messages"][-1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    detail = _extract(client, auth_headers, customer)
    assert [(e["field"], e["quote_verified"]) for e in detail["extractions"]] == [("id_number", False)]  # unknown field dropped
    assert detail["summary"]["unverified"] == 1
    # The customer's name and dates were redacted before the text left KYRO
    assert "Jane Alexandra Doe" not in sent["prompt"] and "14/03/1985" not in sent["prompt"]


def test_extract_requires_ai_to_be_enabled(client, auth_headers, customer):
    document = _upload(client, auth_headers, customer, make_pdf(PASSPORT)).json()
    assert client.post(f"/api/v1/documents/{document['id']}/extract", headers=auth_headers).status_code == 409


# ── Review ───────────────────────────────────────────────────────────────

def _review(client, headers, extraction, **payload):
    return client.put(f"/api/v1/documents/extractions/{extraction['id']}/review", json=payload, headers=headers)


def test_review_accept_edit_reject_and_apply(client, auth_headers, customer, db_session, mock_ai):
    detail = _extract(client, auth_headers, customer)
    fields = {e["field"]: e for e in detail["extractions"]}

    accepted = _review(client, auth_headers, fields["full_name"], decision="ACCEPTED").json()
    assert (accepted["status"], accepted["applied_to_record"]) == ("ACCEPTED", False)
    assert _review(client, auth_headers, fields["id_number"], decision="REJECTED").json()["status"] == "REJECTED"

    # Accepting does not touch the customer record
    db_session.refresh(customer)
    assert customer.country == "GB"

    # An edited value is re-checked; applying it updates the record through the audited customer update
    edited = _review(client, auth_headers, fields["nationality"], decision="ACCEPTED", value="France", apply_to_record=True)
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert (body["status"], body["value"], body["applied_to_record"], body["check_status"]) == ("EDITED", "France", True, "MATCH")
    db_session.refresh(customer)
    assert customer.country == "France"
    assert db_session.query(AuditLog).filter_by(entity_type="CUSTOMER", entity_id=customer.id, action="UPDATE").count() >= 1

    # Fields with no place on the customer record cannot be applied, and rejected values never are
    assert _review(client, auth_headers, fields["expiry_date"], decision="ACCEPTED", apply_to_record=True).status_code == 422
    assert _review(client, auth_headers, fields["date_of_birth"], decision="REJECTED", apply_to_record=True).status_code == 422

    summary = client.get(f"/api/v1/documents/{detail['id']}", headers=auth_headers).json()["summary"]
    assert summary["awaiting_review"] == 2  # date of birth and expiry date


def test_rerunning_extraction_keeps_reviewed_fields(client, auth_headers, customer, mock_ai):
    detail = _extract(client, auth_headers, customer)
    name = next(e for e in detail["extractions"] if e["field"] == "full_name")
    _review(client, auth_headers, name, decision="ACCEPTED")

    again = client.post(f"/api/v1/documents/{detail['id']}/extract", headers=auth_headers).json()
    names = [e for e in again["extractions"] if e["field"] == "full_name"]
    assert [(e["id"], e["status"]) for e in names] == [(name["id"], "ACCEPTED")]
    assert len(again["extractions"]) == 5


def test_document_can_be_linked_to_the_alert_it_supports(client, auth_headers, customer, db_session):
    from app.models.alert import Alert

    other = Customer(full_name="Other Person", email="other.docs@example.com", customer_type="INDIVIDUAL")
    db_session.add(other)
    db_session.flush()
    mine, theirs = Alert(customer_id=customer.id, risk_score=70), Alert(customer_id=other.id, risk_score=70)
    db_session.add_all([mine, theirs])
    db_session.commit()

    assert _upload(client, auth_headers, customer, make_pdf(PASSPORT), alert_id=str(theirs.id)).status_code == 422
    linked = _upload(client, auth_headers, customer, make_pdf(PASSPORT), alert_id=str(mine.id))
    assert linked.status_code == 201
    listed = client.get("/api/v1/documents", params={"alert_id": str(mine.id)}, headers=auth_headers).json()
    assert [d["id"] for d in listed] == [linked.json()["id"]]
    assert db_session.get(Document, linked.json()["id"]).alert_id == mine.id
