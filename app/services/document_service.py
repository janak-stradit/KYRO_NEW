"""
services/document_service.py — Document review copilot (Phase 11.1).

    store      save the file, read its text page by page (no OCR yet)
    extract    the AI reads the fields for the document type, with the page
               and line each value came from
    check      each value is compared with KYRO's own records by plain rules
    review     an analyst accepts, edits or rejects each value; nothing reaches
               the customer record unless they explicitly apply it

The AI never changes a customer record. Files are stored under a generated
name; the uploaded file name is kept for display only.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from dateutil import parser as date_parser
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.ai import AIGateway
from app.config import get_settings
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer
from app.models.document import Document, DocumentExtraction, DocumentPage
from app.schemas.customer import CustomerUpdate
from app.services.audit_service import log_action
from app.services.customer_service import update_customer

MAX_BYTES = 10 * 1024 * 1024
RETENTION_YEARS = 5
_EXTRACT_CHARS = 12000  # text sent to the model per document
_NAME_MATCH = 90  # rapidfuzz score at or above which two names are the same

# Fields the AI is asked for, per document type
FIELDS: dict[str, tuple[str, ...]] = {
    "ID_DOCUMENT": ("full_name", "date_of_birth", "nationality", "id_number", "issue_date", "expiry_date"),
    "PROOF_OF_ADDRESS": ("full_name", "address", "country", "issue_date"),
    "COMPANY_REGISTRY": ("company_name", "registration_number", "incorporation_date", "country", "address", "director", "beneficial_owner"),
    "FINANCIAL_STATEMENT": ("company_name", "period_end", "total_assets", "revenue", "net_income"),
    "SOURCE_OF_FUNDS": ("full_name", "source_of_funds", "amount", "issue_date"),
    "OTHER": ("full_name", "company_name", "date_of_birth", "address", "country", "id_number", "expiry_date"),
}
# Extracted field -> customer column an analyst may choose to update from it
APPLICABLE = {"full_name": "full_name", "company_name": "full_name", "date_of_birth": "date_of_birth", "nationality": "country", "country": "residency_country"}

_PDF, _DOCX, _TEXT = "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


# ── Storage and text ─────────────────────────────────────────────────────

def storage_dir() -> Path:
    path = Path(get_settings().document_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(document: Document) -> Path:
    return storage_dir() / document.storage_key


def _sniff(data: bytes) -> str | None:
    """Decide the type from the content, not from the name or header the browser sent."""
    if data.startswith(b"%PDF-"):
        return _PDF
    if data.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return _DOCX if "word/document.xml" in archive.namelist() else None
        except zipfile.BadZipFile:
            return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return _TEXT if b"\x00" not in data else None


def _pages(data: bytes, content_type: str) -> tuple[list[str], str]:
    """Text per page and the text status. Scanned PDFs have pages but no text."""
    try:
        if content_type == _PDF:
            from pypdf import PdfReader

            pages = [(page.extract_text() or "").strip() for page in PdfReader(io.BytesIO(data)).pages]
            return pages, ("EXTRACTED" if any(pages) else "NEEDS_OCR")
        if content_type == _DOCX:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = ET.fromstring(archive.read("word/document.xml"))
            paragraphs = ["".join(t.text or "" for t in p.iter(f"{_W}t")) for p in root.iter(f"{_W}p")]
            text = "\n".join(p for p in paragraphs if p.strip())
            return [text], ("EXTRACTED" if text else "NEEDS_OCR")
        text = data.decode("utf-8").strip()
        # Form feeds separate pages in plain-text exports
        return [p.strip() for p in text.split("\f")], ("EXTRACTED" if text else "NEEDS_OCR")
    except Exception:  # noqa: BLE001 — a damaged file is stored and reported, not rejected
        return [], "FAILED"


def store(
    db: Session,
    *,
    customer: Customer,
    doc_type: str,
    filename: str,
    data: bytes,
    alert_id: uuid.UUID | None,
    uploaded_by: uuid.UUID,
) -> Document:
    if not data:
        raise DocumentError("The file is empty")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB", 413)
    content_type = _sniff(data)
    if content_type is None:
        raise DocumentError("Only PDF, Word (.docx) and plain-text files can be uploaded", 415)

    pages, text_status = _pages(data, content_type)
    document = Document(
        customer_id=customer.id,
        alert_id=alert_id,
        doc_type=doc_type,
        filename=Path(filename or "document").name[:255],
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=uuid.uuid4().hex,
        page_count=len(pages),
        text_status=text_status,
        uploaded_by=uploaded_by,
        retention_until=date.today() + timedelta(days=365 * RETENTION_YEARS),
    )
    db.add(document)
    db.flush()
    db.add_all(DocumentPage(document_id=document.id, page_number=i, text=text) for i, text in enumerate(pages, start=1))
    file_path(document).write_bytes(data)
    log_action(
        db, entity_type="DOCUMENT", entity_id=document.id, action="CREATE", performed_by=uploaded_by,
        new_values={"customer_id": str(customer.id), "doc_type": doc_type, "filename": document.filename, "sha256": document.sha256},
    )
    db.commit()
    db.refresh(document)
    return document


# ── Checks against KYRO's records ────────────────────────────────────────

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", text).strip().casefold())


def parse_date(value: str) -> date | None:
    try:
        # ISO dates are year-first; other numeric dates in KYC documents are read day-first
        iso = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", value)
        if iso:
            return date(*map(int, iso.groups()))
        return date_parser.parse(value, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def _same_name(a: str, b: str) -> bool:
    return fuzz.token_sort_ratio(_norm(a), _norm(b)) >= _NAME_MATCH


def check(db: Session, customer: Customer, field: str, value: str) -> tuple[str, str | None, str | None]:
    """(check_status, detail, the value on record) for one extracted field."""
    if field in ("full_name", "company_name"):
        record = customer.full_name
        if _same_name(value, record):
            return "MATCH", None, record
        return "MISMATCH", "Name on the document differs from the customer record", record

    if field == "date_of_birth":
        if customer.date_of_birth is None:
            return "NOT_ON_RECORD", "No date of birth on the customer record", None
        parsed = parse_date(value)
        record = customer.date_of_birth.isoformat()
        if parsed is None:
            return "NOT_CHECKED", "Could not read this as a date", record
        return ("MATCH", None, record) if parsed == customer.date_of_birth else ("MISMATCH", "Date of birth differs from the customer record", record)

    if field in ("nationality", "country"):
        record = customer.country if field == "nationality" else (customer.residency_country or customer.country)
        if not record:
            return "NOT_ON_RECORD", "No country on the customer record", None
        return ("MATCH", None, record) if _norm(value) == _norm(record) else ("MISMATCH", "Country differs from the customer record", record)

    if field == "expiry_date":
        parsed = parse_date(value)
        if parsed is None:
            return "NOT_CHECKED", "Could not read this as a date", None
        return ("EXPIRED", f"Expired on {parsed.isoformat()}", None) if parsed < date.today() else ("MATCH", "Not expired", None)

    if field == "beneficial_owner":
        owners = db.query(BeneficialOwner).filter(BeneficialOwner.customer_id == customer.id).all()
        name = re.sub(r"\(.*?\)|\d+(\.\d+)?\s*%", "", value).strip(" ,-")
        match = next((o for o in owners if _same_name(name, o.full_name)), None)
        if match is not None:
            return "MATCH", "In the beneficial ownership register", match.full_name
        return "NOT_ON_RECORD", "Not in the beneficial ownership register", None

    return "NOT_CHECKED", None, None


# ── AI extraction ────────────────────────────────────────────────────────

def extract(db: Session, document: Document, *, requested_by: uuid.UUID | None = None) -> list[DocumentExtraction]:
    """Read the fields from the document text and check each one. Raises AIDisabledError / AIProviderError."""
    pages = db.query(DocumentPage).filter_by(document_id=document.id).order_by(DocumentPage.page_number).all()
    if document.text_status != "EXTRACTED" or not any(p.text for p in pages):
        raise DocumentError("This document has no readable text. Scanned documents need OCR, which is not set up yet.")
    customer = db.get(Customer, document.customer_id)

    text = "\n\n".join(f"[Page {p.page_number}]\n{p.text}" for p in pages)[:_EXTRACT_CHARS]
    wanted = FIELDS[document.doc_type]
    result = AIGateway(db).run(
        "documents.extract_fields",
        {"doc_type": document.doc_type.replace("_", " ").lower(), "fields": ", ".join(wanted), "text": text},
        sensitive={customer.full_name: "PERSON"},
        entity_type="DOCUMENT",
        entity_id=document.id,
        requested_by=requested_by,
    )

    # Re-running replaces what nobody has decided on yet; decisions are kept
    decided = {
        (e.field, _norm(e.value))
        for e in db.query(DocumentExtraction).filter(DocumentExtraction.document_id == document.id, DocumentExtraction.status != "PROPOSED")
    }
    db.query(DocumentExtraction).filter(
        DocumentExtraction.document_id == document.id, DocumentExtraction.status == "PROPOSED"
    ).delete(synchronize_session=False)

    page_text = {p.page_number: _norm(p.text) for p in pages}
    created: list[DocumentExtraction] = []
    seen: set[tuple[str, str]] = set()
    for item in (result.data or {}).get("fields") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip().lower()
        value = str(item.get("value") or "").strip()
        key = (field, _norm(value))
        if field not in wanted or not value or key in seen or key in decided:
            continue
        seen.add(key)

        page = item.get("page") if isinstance(item.get("page"), int) and item.get("page") in page_text else None
        quote = str(item.get("source_quote") or "").strip() or None
        # The value must really be in the document; otherwise it is the model's invention
        where = [page] if page else list(page_text)
        verified = any(_norm(value) in page_text[n] for n in where)
        if verified and page is None:
            page = next(n for n in where if _norm(value) in page_text[n])
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence"))))
        except (TypeError, ValueError):
            confidence = None

        check_status, detail, record_value = check(db, customer, field, value)
        extraction = DocumentExtraction(
            document_id=document.id, field=field, value=value, page_number=page, source_quote=quote,
            quote_verified=verified, confidence=confidence, check_status=check_status, check_detail=detail,
            record_value=record_value, extracted_by=result.provider, ai_interaction_id=result.interaction_id,
        )
        db.add(extraction)
        created.append(extraction)

    document.extracted_at = datetime.now(timezone.utc)
    document.extracted_by = result.provider
    db.commit()
    return created


# ── Analyst review ───────────────────────────────────────────────────────

def review(
    db: Session,
    extraction: DocumentExtraction,
    *,
    decision: str,
    value: str | None,
    apply_to_record: bool,
    user_id: uuid.UUID,
) -> DocumentExtraction:
    document = db.get(Document, extraction.document_id)
    customer = db.get(Customer, document.customer_id)
    edited = decision == "ACCEPTED" and value is not None and value.strip() != extraction.value
    if edited:
        extraction.value = value.strip()
        extraction.check_status, extraction.check_detail, extraction.record_value = check(db, customer, extraction.field, extraction.value)

    extraction.status = "REJECTED" if decision == "REJECTED" else ("EDITED" if edited else "ACCEPTED")
    extraction.reviewed_by = user_id
    extraction.reviewed_at = datetime.now(timezone.utc)

    if apply_to_record:
        if decision != "ACCEPTED":
            raise DocumentError("Only an accepted value can be applied to the customer record")
        column = APPLICABLE.get(extraction.field)
        if column is None:
            raise DocumentError(f"'{extraction.field}' has no field on the customer record to update")
        new_value: Any = extraction.value
        if column == "date_of_birth":
            new_value = parse_date(extraction.value)
            if new_value is None:
                raise DocumentError("Could not read the value as a date")
        # Goes through the normal customer update, so it is audited and re-screens the customer
        update_customer(db, customer, CustomerUpdate(**{column: new_value}), performed_by=user_id)
        extraction.applied_to_record = True
        extraction.check_status, extraction.check_detail, extraction.record_value = check(db, customer, extraction.field, extraction.value)

    log_action(
        db, entity_type="DOCUMENT", entity_id=document.id,
        action="REJECT" if decision == "REJECTED" else "APPROVE", performed_by=user_id,
        new_values={"field": extraction.field, "value": extraction.value, "status": extraction.status, "applied_to_record": extraction.applied_to_record},
    )
    db.commit()
    db.refresh(extraction)
    return extraction


def summary(db: Session, document: Document) -> dict[str, int]:
    rows = db.query(DocumentExtraction).filter_by(document_id=document.id).all()
    return {
        "fields": len(rows),
        "awaiting_review": sum(r.status == "PROPOSED" for r in rows),
        "issues": sum(r.check_status in ("MISMATCH", "EXPIRED", "NOT_ON_RECORD") and r.status != "REJECTED" for r in rows),
        "unverified": sum(not r.quote_verified and r.status != "REJECTED" for r in rows),
    }
