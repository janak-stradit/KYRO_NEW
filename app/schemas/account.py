"""
schemas/account.py — Account and balance history schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AccountType = Literal["CHECKING", "SAVINGS", "INVESTMENT", "TRADING"]
AccountStatus = Literal["ACTIVE", "SUSPENDED", "CLOSED", "FROZEN"]


class AccountCreate(BaseModel):
    customer_id: uuid.UUID
    account_type: AccountType
    currency: str = Field(default="USD", min_length=3, max_length=3)
    balance: float = 0
    opened_date: date | None = None
    account_metadata: dict[str, Any] | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    account_type: AccountType | None = None
    account_status: AccountStatus
    currency: str
    balance: float
    opened_date: date | None = None
    account_metadata: dict[str, Any] | None = None
    risk_flags: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AccountStatusUpdate(BaseModel):
    account_status: AccountStatus


class AccountBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    balance: float | None = None
    available_balance: float | None = None
    currency: str | None = None
    recorded_at: datetime
