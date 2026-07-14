"""
models/customer.py — Customer, risk profile, KYC review, and screening tables.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin


class Customer(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="chk_customer_risk_score"),
        CheckConstraint("kyc_status IN ('PENDING','VERIFIED','REJECTED','UNDER_REVIEW')", name="chk_customer_kyc_status"),
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_customer_risk_level"),
        CheckConstraint("customer_type IN ('INDIVIDUAL','CORPORATE','FUND')", name="chk_customer_type"),
        {"schema": SCHEMA},
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    country: Mapped[str | None] = mapped_column(String(100))
    residency_country: Mapped[str | None] = mapped_column(String(100))
    kyc_status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")
    kyc_last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pep_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sanctions_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adverse_media_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="LOW")
    risk_score: Mapped[int] = mapped_column(nullable=False, default=0)
    customer_type: Mapped[str | None] = mapped_column(String(50))
    customer_metadata: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CustomerRiskProfile(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "customer_risk_profiles"
    __table_args__ = (
        CheckConstraint(
            "risk_category IN ('GEOGRAPHIC','PRODUCT','CHANNEL','BEHAVIORAL')",
            name="chk_risk_profile_category",
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_category: Mapped[str | None] = mapped_column(String(50))
    risk_factor: Mapped[str | None] = mapped_column(String(255))
    risk_weight: Mapped[float | None] = mapped_column(Numeric(5, 2))
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assessed_by: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")


class KYCReview(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "kyc_reviews"
    __table_args__ = (
        CheckConstraint("review_type IN ('PERIODIC','TRIGGERED','ADHOC')", name="chk_kyc_review_type"),
        CheckConstraint(
            "review_status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','OVERDUE')",
            name="chk_kyc_review_status",
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_type: Mapped[str | None] = mapped_column(String(50))
    review_status: Mapped[str] = mapped_column(String(50), nullable=False, default="SCHEDULED")
    scheduled_date: Mapped[date | None] = mapped_column(Date)
    completed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    findings: Mapped[str | None] = mapped_column(Text)
    risk_level_after: Mapped[str | None] = mapped_column(String(20))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PEPSanctionsScreening(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "pep_sanctions_screening"
    __table_args__ = (
        CheckConstraint(
            "screening_type IN ('PEP','SANCTIONS','ADVERSE_MEDIA')", name="chk_screening_type"
        ),
        CheckConstraint(
            "match_status IN ('NO_MATCH','POTENTIAL_MATCH','CONFIRMED_MATCH')",
            name="chk_screening_match_status",
        ),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('CLEARED','ESCALATED','CONFIRMED')",
            name="chk_screening_resolution",
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screening_type: Mapped[str | None] = mapped_column(String(50))
    match_status: Mapped[str | None] = mapped_column(String(50))
    match_details: Mapped[dict | None] = mapped_column(JSONB)
    screened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    screened_by: Mapped[str] = mapped_column(String(50), nullable=False, default="SYSTEM")
    resolution: Mapped[str | None] = mapped_column(String(50))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
