"""
routers/documents.py — Document review copilot (Phase 11.1): upload KYC
documents, have the AI read their fields, check them against KYRO's records
and record the analyst's decision on each value.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai import AIDisabledError, AIProviderError
from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.document import DOCUMENT_TYPES, Document, DocumentExtraction, DocumentPage
from app.models.user import User
from app.services import document_service
from app.services.document_service import APPLICABLE, DocumentError

router = APIRouter(
    prefix="/api/v1/documents", tags=["documents"], dependencies=[Depends(require_permission("cases.view"))]
)


class ExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    field: str
    value: str
    page_number: int | None = None
    source_quote: str | None = None
    quote_verified: bool
    confidence: float | None = None
    check_status: str
    check_detail: str | None = None
    record_value: str | None = None
    status: str
    applied_to_record: bool
    extracted_by: str
    can_apply: bool = False
    reviewed_at: datetime | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    alert_id: uuid.UUID | None = None
    doc_type: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    page_count: int
    text_status: str
    extracted_at: datetime | None = None
    extracted_by: str | None = None
    uploaded_at: datetime
    retention_until: date | None = None
    summary: dict[str, int] = Field(default_factory=dict)


class DocumentDetail(DocumentOut):
    pages: list[dict[str, Any]]
    extractions: list[ExtractionOut]


class ExtractionReview(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED"]
    value: str | None = Field(default=None, min_length=1, max_length=2000)  # an edited value, when accepting
    apply_to_record: bool = False


def _document_or_404(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def _out(db: Session, document: Document) -> dict[str, Any]:
    return {**DocumentOut.model_validate(document).model_dump(), "summary": document_service.summary(db, document)}


def _extraction_out(extraction: DocumentExtraction) -> dict[str, Any]:
    return {**ExtractionOut.model_validate(extraction).model_dump(), "can_apply": extraction.field in APPLICABLE}


def _detail(db: Session, document: Document) -> dict[str, Any]:
    pages = db.query(DocumentPage).filter_by(document_id=document.id).order_by(DocumentPage.page_number).all()
    extractions = (
        db.query(DocumentExtraction).filter_by(document_id=document.id).order_by(DocumentExtraction.page_number, DocumentExtraction.field).all()
    )
    return {
        **_out(db, document),
        "pages": [{"page_number": p.page_number, "text": p.text} for p in pages],
        "extractions": [_extraction_out(e) for e in extractions],
    }


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    customer_id: uuid.UUID = Form(...),
    doc_type: str = Form(...),
    alert_id: uuid.UUID | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents.manage")),
) -> dict[str, Any]:
    """Store a PDF, Word or text document against a customer and read its text."""
    if doc_type not in DOCUMENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"doc_type must be one of {', '.join(DOCUMENT_TYPES)}")
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    if alert_id is not None:
        alert = db.get(Alert, alert_id)
        if alert is None or alert.customer_id != customer.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The alert does not belong to this customer")

    data = await file.read(document_service.MAX_BYTES + 1)
    try:
        document = document_service.store(
            db, customer=customer, doc_type=doc_type, filename=file.filename or "document", data=data,
            alert_id=alert_id, uploaded_by=user.id,
        )
    except DocumentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    return _out(db, document)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    customer_id: uuid.UUID | None = None, alert_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    if customer_id is None and alert_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give a customer_id or an alert_id")
    query = db.query(Document)
    if customer_id:
        query = query.filter(Document.customer_id == customer_id)
    if alert_id:
        query = query.filter(Document.alert_id == alert_id)
    return [_out(db, d) for d in query.order_by(Document.uploaded_at.desc()).all()]


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _detail(db, _document_or_404(db, document_id))


@router.get("/{document_id}/file")
def download_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    document = _document_or_404(db, document_id)
    path = document_service.file_path(document)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The stored file is missing")
    return FileResponse(path, media_type=document.content_type, filename=document.filename)


@router.post("/{document_id}/extract", response_model=DocumentDetail)
def extract_fields(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("documents.manage"))) -> dict[str, Any]:
    """Have the AI read the fields for this document type, then check each against KYRO's records."""
    document = _document_or_404(db, document_id)
    try:
        document_service.extract(db, document, requested_by=user.id)
    except DocumentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return _detail(db, document)


@router.put("/extractions/{extraction_id}/review", response_model=ExtractionOut)
def review_extraction(
    extraction_id: uuid.UUID,
    data: ExtractionReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("documents.manage")),
) -> dict[str, Any]:
    """Accept (optionally with a corrected value) or reject one extracted field."""
    extraction = db.get(DocumentExtraction, extraction_id)
    if extraction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Extracted field not found")
    try:
        extraction = document_service.review(
            db, extraction, decision=data.decision, value=data.value, apply_to_record=data.apply_to_record, user_id=user.id
        )
    except DocumentError as exc:
        db.rollback()
        raise HTTPException(exc.status_code, str(exc)) from None
    return _extraction_out(extraction)
