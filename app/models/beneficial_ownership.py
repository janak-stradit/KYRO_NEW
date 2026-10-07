"""
models/beneficial_ownership.py — UBO (Ultimate Beneficial Owner) capture for
CORPORATE/FUND customers (Phase 4.5).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin


class BeneficialOwner(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "beneficial_owners"
    __table_args__ = (
        CheckConstraint("owner_type IN ('INDIVIDUAL','ENTITY')", name="chk_ubo_owner_type"),
        CheckConstraint(
            "control_type IN ('OWNERSHIP','VOTING_RIGHTS','SENIOR_MANAGEMENT','OTHER')", name="chk_ubo_control_type"
        ),
        CheckConstraint(
            "verification_status IN ('PENDING','VERIFIED','REJECTED')", name="chk_ubo_verification_status"
        ),
        CheckConstraint(
            "ownership_percentage IS NULL OR (ownership_percentage >= 0 AND ownership_percentage <= 100)",
            name="chk_ubo_ownership_pct",
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False, default="INDIVIDUAL")
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(100))
    country_of_residence: Mapped[str | None] = mapped_column(String(100))
    identification_type: Mapped[str | None] = mapped_column(String(50))
    identification_number: Mapped[str | None] = mapped_column(String(100))
    ownership_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    control_type: Mapped[str] = mapped_column(String(20), nullable=False, default="OWNERSHIP")
    control_description: Mapped[str | None] = mapped_column(Text)
    is_pep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sanctions_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str | None] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    last_screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
