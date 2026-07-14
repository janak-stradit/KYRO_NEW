"""
models/warehouse.py — Normalized warehouse tables (schema: warehouse).
Applies 3NF/BCNF: lookup values separated, no transitive dependencies.

Normalization steps applied:
  1NF: Atomic columns, no repeating groups
  2NF: No partial dependencies (all PKs are single-column UUIDs)
  3NF: country/currency/kyc_status/risk_level in lookup tables; no A→B→C chains
  BCNF: Every determinant is a candidate key
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey,
    Index, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipeline.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, SoftDeleteMixin


# ── Lookup tables (3NF: extracted to eliminate redundancy) ────

class Country(Base, UUIDPrimaryKeyMixin):
    """ISO 3166-1 alpha-2 country lookup. Eliminates country name redundancy."""
    __tablename__ = "countries"
    __table_args__ = (
        UniqueConstraint("code", name="uq_country_code"),
        {"schema": "warehouse"},
    )
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    is_high_risk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fatf_category: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(50))


class Currency(Base, UUIDPrimaryKeyMixin):
    """ISO 4217 currency lookup."""
    __tablename__ = "currencies"
    __table_args__ = (
        UniqueConstraint("code", name="uq_currency_code"),
        {"schema": "warehouse"},
    )
    code: Mapped[str] = mapped_column(String(5), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    symbol: Mapped[str | None] = mapped_column(String(10))
    decimal_places: Mapped[int | None] = mapped_column()


class KycStatusLookup(Base, UUIDPrimaryKeyMixin):
    """KYC status values lookup (eliminates string redundancy in 3NF)."""
    __tablename__ = "kyc_statuses"
    __table_args__ = (
        UniqueConstraint("status_code", name="uq_kyc_status_code"),
        {"schema": "warehouse"},
    )
    status_code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    requires_renewal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RiskLevelLookup(Base, UUIDPrimaryKeyMixin):
    """Risk level ordinal lookup."""
    __tablename__ = "risk_levels"
    __table_args__ = (
        UniqueConstraint("level_code", name="uq_risk_level_code"),
        {"schema": "warehouse"},
    )
    level_code: Mapped[str] = mapped_column(String(20), nullable=False)
    ordinal_rank: Mapped[int] = mapped_column(nullable=False)
    min_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)


# ── Core Warehouse Tables ──────────────────────────────────────

class WCustomer(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """
    Warehouse customer (cleaned, normalized, deduplicated).
    SCD Type 2 handled via wh_valid_from / wh_valid_to / wh_is_current.
    """
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("customer_id", "wh_valid_from", name="uq_wh_cust_scd2"),
        Index("ix_wh_cust_id", "customer_id"),
        Index("ix_wh_cust_current", "wh_is_current"),
        Index("ix_wh_cust_risk", "risk_level_id"),
        {"schema": "warehouse"},
    )
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(60))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.countries.id"))
    residency_country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.countries.id"))
    kyc_status_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.kyc_statuses.id"))
    kyc_last_review: Mapped[date | None] = mapped_column(Date)
    pep_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sanctions_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    adverse_media_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_level_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.risk_levels.id"))
    risk_score: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    customer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # SCD Type 2 columns
    wh_valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    wh_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wh_is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw_customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class WAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Warehouse account."""
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_wh_account_id"),
        Index("ix_wh_acc_customer_id", "customer_id"),
        Index("ix_wh_acc_status", "account_status"),
        Index("ix_wh_acc_currency", "currency_id"),
        {"schema": "warehouse"},
    )
    account_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("warehouse.customers.id"), nullable=False
    )
    account_type: Mapped[str] = mapped_column(String(30), nullable=False)
    account_status: Mapped[str] = mapped_column(String(20), nullable=False)
    currency_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.currencies.id"))
    balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    opened_date: Mapped[date | None] = mapped_column(Date)
    raw_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class WTransaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Warehouse transaction (cleaned, typed, partitioned)."""
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_wh_txn_id"),
        CheckConstraint("amount > 0", name="chk_wh_txn_amount"),
        Index("ix_wh_txn_account_id", "account_id"),
        Index("ix_wh_txn_customer_id", "customer_id"),
        Index("ix_wh_txn_date_brin", "transaction_date", postgresql_using="brin"),
        Index("ix_wh_txn_type", "transaction_type"),
        Index("ix_wh_txn_amount", "amount"),
        Index("ix_wh_txn_risk_flags_gin", "risk_flags", postgresql_using="gin"),
        {"schema": "warehouse"},
    )
    transaction_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.customers.id"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.accounts.id"), nullable=False)
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transaction_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.currencies.id"))
    risk_flags: Mapped[list | None] = mapped_column(JSONB)
    source_system: Mapped[str | None] = mapped_column(String(30))
    meta_counterparty: Mapped[str | None] = mapped_column(String(255))
    meta_counterparty_type: Mapped[str | None] = mapped_column(String(30))
    meta_country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.countries.id"))
    meta_destination_country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.countries.id"))
    meta_origin_country_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse.countries.id"))
    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
