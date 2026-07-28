"""
models/raw_data.py — Raw ingestion tables (schema: raw_data).
Stores exact source data with zero transformations plus pipeline audit columns.

Normalization: 1NF — atomic values per cell; semi-structured metadata in JSONB.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, ForeignKey, Index,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pipeline.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RawCustomer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("customer_id", name="uq_raw_customer_id"),
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="chk_raw_risk_score"),
        CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_raw_risk_level"),
        Index("ix_raw_cust_risk_level", "risk_level"),
        Index("ix_raw_cust_kyc_status", "kyc_status"),
        Index("ix_raw_cust_country", "country"),
        {"schema": "raw_data"},
    )
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(60))
    date_of_birth: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(10))
    residency_country: Mapped[str | None] = mapped_column(String(10))
    kyc_status: Mapped[str | None] = mapped_column(String(20))
    kyc_last_review: Mapped[str | None] = mapped_column(String(20))
    pep_flag: Mapped[bool | None] = mapped_column(Boolean)
    sanctions_flag: Mapped[bool | None] = mapped_column(Boolean)
    adverse_media_flag: Mapped[bool | None] = mapped_column(Boolean)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    risk_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    customer_type: Mapped[str | None] = mapped_column(String(30))
    customer_metadata: Mapped[dict | None] = mapped_column(JSONB)
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_file: Mapped[str | None] = mapped_column(String(512))
    batch_id: Mapped[str | None] = mapped_column(String(100))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)


class RawAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_raw_account_id"),
        Index("ix_raw_acc_customer_id", "customer_id"),
        Index("ix_raw_acc_status", "account_status"),
        {"schema": "raw_data"},
    )
    account_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(30))
    account_status: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str | None] = mapped_column(String(5))
    balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    opened_date: Mapped[str | None] = mapped_column(String(20))
    account_metadata: Mapped[dict | None] = mapped_column(JSONB)
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_file: Mapped[str | None] = mapped_column(String(512))
    batch_id: Mapped[str | None] = mapped_column(String(100))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)


class RawTransaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Partitioned by transaction_date RANGE — DDL in migrations."""
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("transaction_id", name="uq_raw_txn_id"),
        CheckConstraint("amount > 0", name="chk_raw_txn_amount_positive"),
        Index("ix_raw_txn_customer_id", "customer_id"),
        Index("ix_raw_txn_account_id", "account_id"),
        Index("ix_raw_txn_type", "transaction_type"),
        Index("ix_raw_txn_date_brin", "transaction_date", postgresql_using="brin"),
        Index("ix_raw_txn_risk_flags_gin", "risk_flags", postgresql_using="gin"),
        {"schema": "raw_data"},
    )
    transaction_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_date: Mapped[str | None] = mapped_column(String(30))
    transaction_type: Mapped[str | None] = mapped_column(String(30))
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(5))
    risk_flags: Mapped[list | None] = mapped_column(JSONB)
    source_system: Mapped[str | None] = mapped_column(String(30))
    meta_counterparty: Mapped[str | None] = mapped_column(String(255))
    meta_counterparty_type: Mapped[str | None] = mapped_column(String(30))
    meta_location: Mapped[str | None] = mapped_column(String(255))
    meta_country: Mapped[str | None] = mapped_column(String(100))
    meta_country_code: Mapped[str | None] = mapped_column(String(5))
    meta_destination_country: Mapped[str | None] = mapped_column(String(5))
    meta_origin_country: Mapped[str | None] = mapped_column(String(5))
    meta_source: Mapped[str | None] = mapped_column(String(50))
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_file: Mapped[str | None] = mapped_column(String(512))
    batch_id: Mapped[str | None] = mapped_column(String(100))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)


class RejectedRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Quarantine table for records that failed validation."""
    __tablename__ = "rejected_records"
    __table_args__ = (
        Index("ix_rejected_entity", "entity_type"),
        Index("ix_rejected_ingestion", "ingestion_id"),
        {"schema": "raw_data"},
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(100))
    ingestion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    batch_id: Mapped[str | None] = mapped_column(String(100))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    reprocessed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
