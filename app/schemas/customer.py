"""
schemas/customer.py — Customer, risk profile, KYC review, and screening schemas.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

KycStatus = Literal["PENDING", "VERIFIED", "REJECTED", "UNDER_REVIEW"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
CustomerType = Literal["INDIVIDUAL", "CORPORATE", "FUND"]


class CustomerBase(BaseModel):
    full_name: str
    email: EmailStr
    phone: str | None = None
    date_of_birth: date | None = None
    country: str | None = None
    residency_country: str | None = None
    customer_type: CustomerType | None = None
    customer_metadata: dict[str, Any] | None = None


class CustomerCreate(CustomerBase):
    pep_flag: bool = False
    sanctions_flag: bool = False
    adverse_media_flag: bool = False


class CustomerUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    country: str | None = None
    residency_country: str | None = None
    kyc_status: KycStatus | None = None
    pep_flag: bool | None = None
    sanctions_flag: bool | None = None
    adverse_media_flag: bool | None = None
    risk_level: RiskLevel | None = None
    risk_score: int | None = Field(default=None, ge=0, le=100)
    customer_type: CustomerType | None = None
    customer_metadata: dict[str, Any] | None = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kyc_status: KycStatus
    kyc_last_review: datetime | None = None
    pep_flag: bool
    sanctions_flag: bool
    adverse_media_flag: bool
    risk_level: RiskLevel
    risk_score: int
    created_at: datetime
    updated_at: datetime


class RiskProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    risk_category: str | None = None
    risk_factor: str | None = None
    risk_weight: float | None = None
    assessed_at: datetime
    assessed_by: str


class KYCReviewCreate(BaseModel):
    review_type: Literal["PERIODIC", "TRIGGERED", "ADHOC"] | None = None
    scheduled_date: date | None = None
    findings: str | None = None


class KYCReviewUpdate(BaseModel):
    review_status: Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "OVERDUE"] | None = None
    completed_date: datetime | None = None
    findings: str | None = None
    risk_level_after: RiskLevel | None = None


class KYCReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    review_type: str | None = None
    review_status: str
    scheduled_date: date | None = None
    completed_date: datetime | None = None
    findings: str | None = None
    risk_level_after: str | None = None
    reviewed_by: uuid.UUID | None = None
    created_at: datetime


class ScreeningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    screening_type: str | None = None
    match_status: str | None = None
    match_details: dict[str, Any] | None = None
    screened_at: datetime
    screened_by: str
    resolution: str | None = None
    resolved_at: datetime | None = None
