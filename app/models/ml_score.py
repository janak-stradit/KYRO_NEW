"""
models/ml_score.py — Persisted output of the ML scoring pipeline (Phase 2).
Kept separate from Transaction.risk_score/risk_flags (the Phase 1 deterministic
rules-engine output) so the two scoring systems don't conflate.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class MLScore(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ml_scores"
    __table_args__ = (
        CheckConstraint("combined_score >= 0 AND combined_score <= 100", name="chk_ml_score_range"),
        {"schema": SCHEMA},
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    risk_scorer_version: Mapped[int | None] = mapped_column(Integer)
    anomaly_classifier_version: Mapped[int | None] = mapped_column(Integer)
    isolation_detector_version: Mapped[int | None] = mapped_column(Integer)
    is_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    rf_risk_score: Mapped[float | None] = mapped_column(Float)
    anomaly_probability: Mapped[float | None] = mapped_column(Float)
    isolation_score: Mapped[float | None] = mapped_column(Float)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    explanation: Mapped[dict | None] = mapped_column(JSONB)
    features: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
