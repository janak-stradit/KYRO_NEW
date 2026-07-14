"""
schemas/alert.py — Alert queue schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

AlertStatus = Literal["OPEN", "ASSIGNED", "IN_REVIEW", "RESOLVED", "ESCALATED"]
RecommendedAction = Literal[
    "REVIEW", "ENHANCED_DUE_DILIGENCE", "SAR", "CLOSE", "BATCH_REVIEW", "IMMEDIATE_REVIEW"
]


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    alert_type: str | None = None
    risk_score: int
    confidence: float | None = None
    triggered_rules: dict[str, Any] | list[Any] | None = None
    ml_explanation: dict[str, Any] | None = None
    recommended_action: RecommendedAction | None = None
    status: AlertStatus
    assigned_to: uuid.UUID | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
    resolution_notes: str | None = None
    is_false_positive: bool | None = None
    ml_version: str | None = None


class AlertAssign(BaseModel):
    assigned_to: uuid.UUID


class AlertResolve(BaseModel):
    resolution_notes: str
    is_false_positive: bool | None = None


class AlertEscalate(BaseModel):
    resolution_notes: str | None = None
