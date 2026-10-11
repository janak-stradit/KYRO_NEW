"""
models/fx_rate.py — Daily exchange rates into the base currency (settings.base_currency),
so the rules engine compares amounts in one currency.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class FxRate(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("rate_date", "currency", name="uq_fx_rate_date_currency"), {"schema": SCHEMA})

    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_to_base: Mapped[float] = mapped_column(Numeric(20, 10), nullable=False)  # 1 unit of currency = this much base
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
