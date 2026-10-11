"""
schemas/transaction.py — Transaction ingestion and risk-assessment schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TransactionType = Literal["DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE"]
Direction = Literal["CREDIT", "DEBIT"]
Channel = Literal["CASH", "WIRE", "ACH", "CARD", "CHEQUE", "INTERNAL", "CRYPTO", "OTHER"]


class TransactionCreate(BaseModel):
    customer_id: uuid.UUID
    account_id: uuid.UUID
    transaction_date: datetime
    # Either a KYRO type, or the source's own code (source_code) mapped in Data > Transaction codes
    transaction_type: TransactionType | None = None
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
    # Rules engine R2
    direction: Direction | None = None
    channel: Channel | None = None
    counterparty_account: str | None = Field(default=None, max_length=100)
    counterparty_bank_bic: str | None = Field(default=None, pattern=r"^[A-Za-z]{6}[A-Za-z0-9]{2}([A-Za-z0-9]{3})?$")
    counterparty_country: str | None = Field(default=None, max_length=100)
    branch_id: str | None = Field(default=None, max_length=50)
    depositor_name: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=100)
    source_code: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def _type_or_code(self) -> "TransactionCreate":
        if self.transaction_type is None and not self.source_code:
            raise ValueError("Give a transaction_type, or the source system's source_code")
        return self


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
    amount_base: float | None = None
    direction: str | None = None
    channel: str | None = None
    counterparty_account: str | None = None
    counterparty_bank_bic: str | None = None
    counterparty_country: str | None = None
    branch_id: str | None = None
    reference: str | None = None
    source_code: str | None = None
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
