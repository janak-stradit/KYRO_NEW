"""
models/transaction.py — Transaction, counterparty, and risk flag tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class Transaction(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_transaction_amount_positive"),
        CheckConstraint(
            "transaction_type IS NULL OR transaction_type IN ('DEPOSIT','WITHDRAWAL','TRANSFER','FX','TRADE')",
            name="chk_transaction_type",
        ),
        Index("ix_app_txn_date_brin", "transaction_date", postgresql_using="brin"),
        Index("ix_app_txn_risk_flags_gin", "risk_flags", postgresql_using="gin"),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_type: Mapped[str | None] = mapped_column(String(50))
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    meta_counterparty: Mapped[str | None] = mapped_column(String(255))
    meta_counterparty_type: Mapped[str | None] = mapped_column(String(50))
    meta_location: Mapped[str | None] = mapped_column(String(255))
    meta_country: Mapped[str | None] = mapped_column(String(100))
    meta_country_code: Mapped[str | None] = mapped_column(String(3))
    meta_destination_country: Mapped[str | None] = mapped_column(String(100))
    meta_origin_country: Mapped[str | None] = mapped_column(String(100))
    meta_source: Mapped[str | None] = mapped_column(String(100))
    risk_flags: Mapped[dict | None] = mapped_column(JSONB)
    risk_score: Mapped[int] = mapped_column(nullable=False, default=0)
    source_system: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TransactionCounterparty(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "transaction_counterparties"
    __table_args__ = ({"schema": SCHEMA},)

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    counterparty_type: Mapped[str | None] = mapped_column(String(50))
    counterparty_country: Mapped[str | None] = mapped_column(String(100))
    counterparty_account: Mapped[str | None] = mapped_column(String(100))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_country: Mapped[str | None] = mapped_column(String(100))
    relationship_to_customer: Mapped[str | None] = mapped_column(String(100))


class TransactionRiskFlag(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "transaction_risk_flags"
    __table_args__ = (
        CheckConstraint(
            "flag_severity IS NULL OR flag_severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="chk_txn_flag_severity",
        ),
        {"schema": SCHEMA},
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag_type: Mapped[str | None] = mapped_column(String(100))
    flag_description: Mapped[str | None] = mapped_column(Text)
    flag_severity: Mapped[str | None] = mapped_column(String(20))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, default="RULES_ENGINE")
