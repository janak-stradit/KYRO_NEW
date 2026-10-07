"""
schemas/watchlist.py — response models for the watchlist sources/entities/
ingestion-run history endpoints.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WatchlistSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    list_category: str
    url: str
    is_enabled: bool
    last_fetched_at: datetime | None = None
    last_success_at: datetime | None = None
    last_file_hash: str | None = None


class WatchlistEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    external_id: str
    entity_type: str
    primary_name: str
    aka_names: list[str] | None = None
    date_of_birth: date | None = None
    nationalities: list[str] | None = None
    programs: list[str] | None = None
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime


class WatchlistIngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    records_seen: int
    records_added: int
    records_updated: int
    records_deactivated: int
    error_message: str | None = None


class IngestRequest(BaseModel):
    run_async: bool = True


class IngestResponse(BaseModel):
    status: str
    task_id: str | None = None
    result: dict[str, Any] | None = None
