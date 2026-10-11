"""
models/alert.py — Alert table (analyst work queue for triggered risk rules).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
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
        CheckConstraint(
            "resolution_outcome IS NULL OR resolution_outcome IN "
            "('SAR_FILED','ESCALATED','TRUE_POSITIVE_NO_SAR','FALSE_POSITIVE')",
            name="chk_alert_resolution_outcome",
        ),
        CheckConstraint("qa_result IS NULL OR qa_result IN ('PASS','FAIL')", name="chk_alert_qa_result"),
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
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the team routing chose (models/assignment.py)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    is_false_positive: Mapped[bool | None] = mapped_column(Boolean)
    # Disposition taxonomy (schemas/alert.py): one outcome, one or more reason codes
    resolution_outcome: Mapped[str | None] = mapped_column(String(30), index=True)
    resolution_reasons: Mapped[list | None] = mapped_column(JSONB)
    sar_reference: Mapped[str | None] = mapped_column(String(100))
    # Quality check on the resolved case (does not change the outcome)
    qa_result: Mapped[str | None] = mapped_column(String(10))
    qa_notes: Mapped[str | None] = mapped_column(Text)
    qa_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    qa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Generated case summary (routers/case_file.py); regenerated on request, never edited in place
    summary: Mapped[str | None] = mapped_column(Text)
    summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary_provider: Mapped[str | None] = mapped_column(String(30))
    # The AI call that wrote the summary, and the investigator who checked it against the records
    summary_interaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary_attested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    summary_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ml_version: Mapped[str | None] = mapped_column(String(20))
    # Provenance: which rule configuration produced the alert, with what values, from which transactions
    rule_version: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    evidence_transaction_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    # Deadlines (services/deadline_service.py); days are fixed when each clock starts
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # date of initial detection
    sla_days: Mapped[int | None] = mapped_column()
    sar_candidate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # escalated as a potential SAR
    sar_decision_days: Mapped[int | None] = mapped_column()
    filing_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
