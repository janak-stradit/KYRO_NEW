"""
schemas/beneficial_ownership.py — UBO capture request/response models
(Phase 4.5).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OwnerType = Literal["INDIVIDUAL", "ENTITY"]
ControlType = Literal["OWNERSHIP", "VOTING_RIGHTS", "SENIOR_MANAGEMENT", "OTHER"]
VerificationStatus = Literal["PENDING", "VERIFIED", "REJECTED"]


class BeneficialOwnerBase(BaseModel):
    owner_type: OwnerType = "INDIVIDUAL"
    full_name: str
    date_of_birth: date | None = None
    nationality: str | None = None
    country_of_residence: str | None = None
    identification_type: str | None = None
    identification_number: str | None = None
    ownership_percentage: float | None = Field(default=None, ge=0, le=100)
    control_type: ControlType = "OWNERSHIP"
    control_description: str | None = None
    is_pep: bool = False
    source: str | None = None
    effective_from: date | None = None


class BeneficialOwnerCreate(BeneficialOwnerBase):
    pass


class BeneficialOwnerUpdate(BaseModel):
    full_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    country_of_residence: str | None = None
    identification_type: str | None = None
    identification_number: str | None = None
    ownership_percentage: float | None = Field(default=None, ge=0, le=100)
    control_type: ControlType | None = None
    control_description: str | None = None
    is_pep: bool | None = None
    source: str | None = None


class BeneficialOwnerVerify(BaseModel):
    verification_status: Literal["VERIFIED", "REJECTED"]
    notes: str | None = None


class BeneficialOwnerOut(BeneficialOwnerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    sanctions_flag: bool
    verification_status: VerificationStatus
    verified_at: datetime | None = None
    verified_by: uuid.UUID | None = None
    effective_to: date | None = None
    last_screened_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UBOSummaryOut(BaseModel):
    customer_id: uuid.UUID
    owner_count: int
    total_ownership_percentage: float
    verified_count: int
    pending_count: int
    rejected_count: int
    sanctioned_count: int
    is_cdd_complete: bool
