"""
models/account.py — Account, account metadata, and account balance history tables.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class Account(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('CHECKING','SAVINGS','INVESTMENT','TRADING')", name="chk_account_type"
        ),
        CheckConstraint(
            "account_status IN ('ACTIVE','SUSPENDED','CLOSED','FROZEN')", name="chk_account_status"
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_type: Mapped[str | None] = mapped_column(String(50))
    account_status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    balance: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    opened_date: Mapped[date | None] = mapped_column(Date)
    account_metadata: Mapped[dict | None] = mapped_column(JSONB)
    risk_flags: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AccountMetadata(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "account_metadata"
    __table_args__ = (
        CheckConstraint(
            "meta_type IS NULL OR meta_type IN ('STRING','NUMBER','BOOLEAN','JSON')",
            name="chk_account_meta_type",
        ),
        {"schema": SCHEMA},
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meta_key: Mapped[str | None] = mapped_column(String(100))
    meta_value: Mapped[str | None] = mapped_column(Text)
    meta_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AccountBalance(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "account_balances"
    __table_args__ = ({"schema": SCHEMA},)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    available_balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
