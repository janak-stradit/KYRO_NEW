"""
schemas/regulatory.py — Regulatory knowledge base schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RegulatorySourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    source_kind: str
    jurisdiction: str
    config: dict[str, Any]
    is_enabled: bool
    last_fetched_at: datetime | None = None
    last_success_at: datetime | None = None


class RegulatoryIngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    as_of: str | None = None
    sections_seen: int
    sections_added: int
    sections_changed: int
    sections_removed: int
    error_message: str | None = None


class RegulatorySectionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    section_ref: str
    heading: str | None = None
    version: str
    url: str | None = None
    is_current: bool
    first_seen_at: datetime
    superseded_at: datetime | None = None


class RegulatorySectionOut(RegulatorySectionSummary):
    content: str
    source_note: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskSource(BaseModel):
    source_ref: str
    source_type: str
    title: str | None = None
    version: str
    url: str | None = None
    excerpt: str
    coverage: float


class AskResponse(BaseModel):
    question: str
    mode: str  # NOT_FOUND | GENERATED | EXTRACTIVE
    answer: str | None = None
    citations: list[str]
    verified: bool
    sources: list[AskSource]
    interaction_id: str | None = None
    warnings: list[str]


ObligationCategory = Literal[
    "REPORTING", "RECORDKEEPING", "CUSTOMER_IDENTIFICATION", "PROGRAM", "MONITORING", "OTHER"
]


class ObligationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    section_id: uuid.UUID
    section_ref: str
    section_version: str
    obligated_party: str
    action: str
    deadline: str | None = None
    condition: str | None = None
    category: str
    source_quote: str | None = None
    quote_verified: bool
    status: str
    extracted_by: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None


class ObligationReview(BaseModel):
    """A reviewer's decision. Any field given here replaces the proposed value."""

    decision: Literal["CONFIRMED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)
    obligated_party: str | None = Field(default=None, min_length=1, max_length=255)
    action: str | None = Field(default=None, min_length=1)
    deadline: str | None = Field(default=None, max_length=255)
    condition: str | None = None
    category: ObligationCategory | None = None


class ObligationExtractResult(BaseModel):
    sections_processed: int
    sections_skipped: int
    obligations_proposed: int
    extracted_by: str


class ObligationSummary(BaseModel):
    by_status: dict[str, int]
    by_category: dict[str, int]
    unverified_quotes: int


class MappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    obligation_id: uuid.UUID
    control_code: str
    rationale: str | None = None
    status: str
    proposed_by: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None


class MappingCreate(BaseModel):
    obligation_id: uuid.UUID
    control_code: str
    rationale: str | None = Field(default=None, max_length=2000)


class MappingReview(BaseModel):
    decision: Literal["CONFIRMED", "REJECTED"]


class ControlOut(BaseModel):
    code: str
    kind: str
    name: str
    description: str
    config_keys: list[str]
