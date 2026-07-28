"""
schemas/ml.py — Request/response schemas for the ML scoring API.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel


class ScoreTransactionRequest(BaseModel):
    transaction_id: uuid.UUID


class ScoreTransactionResponse(BaseModel):
    transaction_id: uuid.UUID
    risk_score: float
    anomaly_flag: bool
    confidence: float
    ml_explanation: dict[str, Any]
    alert_created: bool
    alert_id: uuid.UUID | None = None
    recommended_action: str


class ScoreBatchRequest(BaseModel):
    transaction_ids: list[uuid.UUID]


class ScoreBatchItem(BaseModel):
    transaction_id: uuid.UUID
    risk_score: float
    anomaly_flag: bool


class ScoreCustomerResponse(BaseModel):
    customer_id: uuid.UUID
    overall_risk: float
    risk_level: str | None = None
    behavioral_anomalies: list[dict[str, Any]]
    trend_summary: str
    recommendation: str | None = None


class TrainRequest(BaseModel):
    as_candidate: bool = False
    candidate_traffic_pct: float = 10.0
    limit: int | None = None
    run_async: bool = False


class TrainResponse(BaseModel):
    status: Literal["COMPLETED", "QUEUED"]
    task_id: str | None = None
    versions: dict[str, int] | None = None
    metrics: dict[str, Any] | None = None


class ModelStatus(BaseModel):
    name: str
    active_version: int | None = None
    candidate_version: int | None = None
    candidate_traffic_pct: float = 0.0
    available_versions: list[int]


class PerformanceResponse(BaseModel):
    precision: float | None = None
    false_positive_rate: float | None = None
    total_reviewed: int
    window_days: int
