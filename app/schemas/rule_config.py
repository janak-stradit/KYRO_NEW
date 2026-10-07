"""
schemas/rule_config.py — request/response models for the rule threshold
override API (Phase 4.4).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RuleConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    jurisdiction: str
    value: dict[str, Any]
    description: str | None = None
    is_active: bool
    updated_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class RuleConfigUpdate(BaseModel):
    value: Any
    jurisdiction: str | None = None
    description: str | None = None
