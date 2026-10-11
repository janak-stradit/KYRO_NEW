"""
models/data_foundation.py — What the rules engine needs to know about the data
it is given (rules engine R2, docs/plans/RULES_ENGINE_IMPLEMENTATION_PHASES.md).

TransactionCodeMap   a source system's own transaction code → KYRO type,
                     direction and channel; proposed by one person, approved
                     by another before it is used
DataReconciliation   per load or per source and day: what was received, what
                     was stored, what the rules engine evaluated
CustomerExpectedActivity  what the customer said their account would be used
                     for, captured at onboarding or review
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

DIRECTIONS = ("CREDIT", "DEBIT")
CHANNELS = ("CASH", "WIRE", "ACH", "CARD", "CHEQUE", "INTERNAL", "CRYPTO", "OTHER")
TRANSACTION_TYPES = ("DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE")
SEGMENTS = ("RETAIL", "HNW", "SOLE_TRADER", "SME", "CORPORATE", "FUND", "MSB", "NPO", "CORRESPONDENT")
CODE_MAP_STATUSES = ("PENDING", "ACTIVE", "REJECTED", "RETIRED")


class TransactionCodeMap(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "transaction_code_maps"
    __table_args__ = (
        CheckConstraint(f"status IN {CODE_MAP_STATUSES}", name="chk_code_map_status"),
        CheckConstraint(f"transaction_type IN {TRANSACTION_TYPES}", name="chk_code_map_type"),
        CheckConstraint(f"direction IS NULL OR direction IN {DIRECTIONS}", name="chk_code_map_direction"),
        CheckConstraint(f"channel IS NULL OR channel IN {CHANNELS}", name="chk_code_map_channel"),
        # One live meaning per code
        Index("uq_code_map_active", "source_system", "source_code", unique=True, postgresql_where=text("status = 'ACTIVE'")),
        {"schema": SCHEMA},
    )

    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    source_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(10))
    channel: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)


class DataReconciliation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "data_reconciliations"
    __table_args__ = (
        CheckConstraint("kind IN ('FEED_LOAD', 'DAILY_SOURCE')", name="chk_reconciliation_kind"),
        {"schema": SCHEMA},
    )

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)  # feed file name or source system
    business_date: Mapped[date | None] = mapped_column(Date, index=True)
    feed_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    received_count: Mapped[int | None] = mapped_column(Integer)
    received_amount: Mapped[float | None] = mapped_column(Numeric(20, 2))
    stored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stored_amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    evaluated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_existing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balanced: Mapped[bool] = mapped_column(nullable=False, default=False)
    issues: Mapped[list | None] = mapped_column(JSONB)  # what does not add up, in words
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerExpectedActivity(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "customer_expected_activity"
    __table_args__ = ({"schema": SCHEMA},)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    monthly_credit_value: Mapped[float | None] = mapped_column(Numeric(18, 2))   # in the base currency
    monthly_debit_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    monthly_transaction_count: Mapped[int | None] = mapped_column(Integer)
    cash_share_percent: Mapped[int | None] = mapped_column(Integer)
    countries: Mapped[list | None] = mapped_column(JSONB)              # countries the customer expects to deal with
    purpose: Mapped[str | None] = mapped_column(Text)                  # stated purpose of the account
    source: Mapped[str | None] = mapped_column(String(30))             # ONBOARDING | PERIODIC_REVIEW | FEED
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
