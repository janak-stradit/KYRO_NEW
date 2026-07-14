"""
models/alert.py — Alert table (analyst work queue for triggered risk rules).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class Alert(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "recommended_action IS NULL OR recommended_action IN "
            "('REVIEW','ENHANCED_DUE_DILIGENCE','SAR','CLOSE',"
            "'BATCH_REVIEW','IMMEDIATE_REVIEW')",
            name="chk_alert_recommended_action",
        ),
        CheckConstraint(
            "status IN ('OPEN','ASSIGNED','IN_REVIEW','RESOLVED','ESCALATED')",
            name="chk_alert_status",
        ),
        {"schema": SCHEMA},
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alert_type: Mapped[str | None] = mapped_column(String(100))
    risk_score: Mapped[int] = mapped_column(nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    triggered_rules: Mapped[dict | None] = mapped_column(JSONB)
    ml_explanation: Mapped[dict | None] = mapped_column(JSONB)
    recommended_action: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="OPEN")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    is_false_positive: Mapped[bool | None] = mapped_column(Boolean)
    ml_version: Mapped[str | None] = mapped_column(String(20))
