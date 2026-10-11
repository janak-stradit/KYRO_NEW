"""
models/obligation.py — Obligations register (Phase 11.3 step 4): who must do
what, by when, under which section and version.

The AI proposes obligations from section text; a compliance officer confirms,
edits or rejects each one. Every obligation keeps the sentence it was drawn
from, and `quote_verified` says whether that sentence really is in the section.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin

OBLIGATION_STATUSES = ("PROPOSED", "CONFIRMED", "REJECTED", "SUPERSEDED")
OBLIGATION_CATEGORIES = (
    "REPORTING", "RECORDKEEPING", "CUSTOMER_IDENTIFICATION", "PROGRAM", "MONITORING", "OTHER",
)


class Obligation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "obligations"
    __table_args__ = (
        CheckConstraint(f"status IN {OBLIGATION_STATUSES}", name="chk_obligation_status"),
        CheckConstraint(f"category IN {OBLIGATION_CATEGORIES}", name="chk_obligation_category"),
        Index("ix_app_obligations_section_ref", "section_ref"),
        Index("ix_app_obligations_status", "status"),
        {"schema": SCHEMA},
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_sections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    section_version: Mapped[str] = mapped_column(String(50), nullable=False)

    obligated_party: Mapped[str] = mapped_column(String(255), nullable=False)  # who
    action: Mapped[str] = mapped_column(Text, nullable=False)  # must do what
    deadline: Mapped[str | None] = mapped_column(String(255))  # by when
    condition: Mapped[str | None] = mapped_column(Text)  # when it applies
    category: Mapped[str] = mapped_column(String(30), nullable=False, default="OTHER")

    source_quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED")
    extracted_by: Mapped[str] = mapped_column(String(30), nullable=False)  # provider name, e.g. "mock"
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
