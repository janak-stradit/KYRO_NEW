"""
models/change_management.py — Regulatory change management (Phase 11.5).

RegulatoryChange: one row each time an ingestion finds a section added,
amended or removed, with a snapshot of the obligations and controls it
touches. RuleConfigChange: a proposed change to a rule threshold that a
second person must approve before it takes effect on its effective date.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

REGULATORY_CHANGE_TYPES = ("ADDED", "AMENDED", "REMOVED")
REGULATORY_CHANGE_STATUSES = ("OPEN", "ACTION_REQUIRED", "NO_ACTION", "CLOSED")
RULE_CHANGE_STATUSES = ("PENDING_APPROVAL", "APPROVED", "REJECTED", "ACTIVE", "CANCELLED")


class RegulatoryChange(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "regulatory_changes"
    __table_args__ = (
        CheckConstraint(f"change_type IN {REGULATORY_CHANGE_TYPES}", name="chk_regulatory_change_type"),
        CheckConstraint(f"status IN {REGULATORY_CHANGE_STATUSES}", name="chk_regulatory_change_status"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_ingestion_runs.id", ondelete="SET NULL")
    )
    section_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    heading: Mapped[str | None] = mapped_column(String(500))
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    old_section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    new_section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    old_version: Mapped[str | None] = mapped_column(String(50))
    new_version: Mapped[str | None] = mapped_column(String(50))
    # What the change touched when it was detected: obligations, controls, rule config keys
    affected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    assessment_notes: Mapped[str | None] = mapped_column(Text)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RuleConfigChange(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "rule_config_changes"
    __table_args__ = (
        CheckConstraint(f"status IN {RULE_CHANGE_STATUSES}", name="chk_rule_config_change_status"),
        {"schema": SCHEMA},
    )

    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default="GLOBAL")
    previous_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # {"value": ...} when proposed
    proposed_value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    regulatory_change_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.regulatory_changes.id", ondelete="SET NULL")
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    backtest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING_APPROVAL", index=True)
    proposed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
