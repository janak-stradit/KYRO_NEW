"""
models/regulatory.py — Regulatory knowledge base (Phase 11.3): sources,
ingestion run history and versioned section text.

A section's text is never overwritten. When an ingestion finds different text
for a section, the old row stops being current and a new row is added, so
KYRO can show what a rule said on any date and what changed (Phase 11.5).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin


class RegulatorySource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "regulatory_sources"
    __table_args__ = (
        CheckConstraint("source_kind IN ('ECFR')", name="chk_regulatory_source_kind"),
        {"schema": SCHEMA},
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    # What to fetch, e.g. {"title": 31, "part": "1023"} or {..., "section": "240.17a-8"}
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_content_hash: Mapped[str | None] = mapped_column(String(64))


class RegulatoryIngestionRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "regulatory_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SUCCESS','FAILED','SKIPPED_UNCHANGED')", name="chk_regulatory_run_status"
        ),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    as_of: Mapped[str | None] = mapped_column(String(20))  # date the source says its text is current to
    content_hash: Mapped[str | None] = mapped_column(String(64))
    sections_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sections_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sections_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sections_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class RegulatorySection(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "regulatory_sections"
    __table_args__ = (
        Index("ix_app_regulatory_sections_ref", "source_id", "section_ref"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_ingestion_runs.id", ondelete="SET NULL")
    )
    section_ref: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "31 CFR 1023.320"
    heading: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)  # date this text was last amended
    url: Mapped[str | None] = mapped_column(Text)
    source_note: Mapped[str | None] = mapped_column(Text)  # amendment history as published
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
