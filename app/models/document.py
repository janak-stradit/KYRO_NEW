"""
models/document.py — Document review copilot (Phase 11.1).

Document: an uploaded KYC file linked to a customer (and optionally the alert
it was collected for). DocumentPage: its text, page by page, so every
extracted value can point at the page it came from. DocumentExtraction: one
field the AI read from the document, the result of checking it against
KYRO's records, and the analyst's decision on it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

DOCUMENT_TYPES = ("ID_DOCUMENT", "PROOF_OF_ADDRESS", "COMPANY_REGISTRY", "FINANCIAL_STATEMENT", "SOURCE_OF_FUNDS", "OTHER")
TEXT_STATUSES = ("EXTRACTED", "NEEDS_OCR", "UNSUPPORTED", "FAILED")
CHECK_STATUSES = ("MATCH", "MISMATCH", "NOT_ON_RECORD", "EXPIRED", "NOT_CHECKED")
EXTRACTION_STATUSES = ("PROPOSED", "ACCEPTED", "EDITED", "REJECTED")


class Document(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"doc_type IN {DOCUMENT_TYPES}", name="chk_document_type"),
        CheckConstraint(f"text_status IN {TEXT_STATUSES}", name="chk_document_text_status"),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.alerts.id", ondelete="SET NULL"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(30), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # as uploaded, for display only
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(100), nullable=False)  # file name inside the storage directory
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text_status: Mapped[str] = mapped_column(String(20), nullable=False)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_by: Mapped[str | None] = mapped_column(String(30))  # provider that read the fields, e.g. "mock"
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    retention_until: Mapped[date | None] = mapped_column(Date)


class DocumentPage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
        {"schema": SCHEMA},
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentExtraction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "document_extractions"
    __table_args__ = (
        CheckConstraint(f"check_status IN {CHECK_STATUSES}", name="chk_document_extraction_check"),
        CheckConstraint(f"status IN {EXTRACTION_STATUSES}", name="chk_document_extraction_status"),
        {"schema": SCHEMA},
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    source_quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 2))

    # Deterministic comparison with KYRO's own records
    check_status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_CHECKED")
    check_detail: Mapped[str | None] = mapped_column(Text)
    record_value: Mapped[str | None] = mapped_column(Text)

    # The analyst's decision
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED")
    applied_to_record: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extracted_by: Mapped[str] = mapped_column(String(30), nullable=False)
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
