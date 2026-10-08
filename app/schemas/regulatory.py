"""
schemas/regulatory.py — Regulatory knowledge base schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

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
