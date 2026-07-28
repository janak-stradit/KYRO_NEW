"""
schemas/transaction.py — Transaction ingestion and risk-assessment schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TransactionType = Literal["DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE"]


class TransactionCreate(BaseModel):
    customer_id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: datetime
    transaction_type: TransactionType
    amount: float = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    meta_counterparty: str | None = None
    meta_counterparty_type: str | None = None
    meta_location: str | None = None
    meta_country: str | None = None
    meta_country_code: str | None = None
    meta_destination_country: str | None = None
    meta_origin_country: str | None = None
    meta_source: str | None = None
    source_system: str | None = None


class TransactionBatchCreate(BaseModel):
    transactions: list[TransactionCreate]


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: datetime
    transaction_type: str | None = None
    amount: float
    currency: str
    meta_counterparty: str | None = None
    meta_counterparty_type: str | None = None
    meta_country: str | None = None
    risk_flags: dict[str, Any] | None = None
    risk_score: int
    source_system: str | None = None
    created_at: datetime


class TransactionRiskOut(BaseModel):
    transaction_id: uuid.UUID
    risk_score: int
    risk_flags: dict[str, Any] | None = None
    triggered_rules: list[str]


class TransactionFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    flag_type: str | None = None
    flag_description: str | None = None
    flag_severity: str | None = None
    triggered_at: datetime
    triggered_by: str
