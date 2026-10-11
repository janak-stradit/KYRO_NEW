"""
models/regulatory_notice.py — Rules and proposed rules published in the
Federal Register that amend a CFR part KYRO has loaded (Phase 11.5).

A proposed rule is the early warning: it appears here before the regulation
text changes, with its comment and effective dates, so compliance can assess
it ahead of time.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

NOTICE_STATUSES = ("NEW", "ACTION_REQUIRED", "NO_ACTION", "CLOSED")


class RegulatoryNotice(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "regulatory_notices"
    __table_args__ = (
        CheckConstraint(f"status IN {NOTICE_STATUSES}", name="chk_regulatory_notice_status"),
        {"schema": SCHEMA},
    )

    document_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notice_type: Mapped[str] = mapped_column(String(30), nullable=False)  # "Rule" | "Proposed Rule"
    action: Mapped[str | None] = mapped_column(Text)  # e.g. "Final rule.", "Proposed rule; withdrawal."
    abstract: Mapped[str | None] = mapped_column(Text)
    agencies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_on: Mapped[date | None] = mapped_column(Date)
    comments_close_on: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # Loaded CFR parts this notice amends, e.g. ["31 CFR Part 1010"]
    matched_parts: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW", index=True)
    assessment_notes: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
