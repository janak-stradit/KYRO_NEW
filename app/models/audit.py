"""
models/audit.py — Immutable audit log of mutations across app entities.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT')", name="chk_audit_entity_type"
        ),
        CheckConstraint(
            "action IN ('CREATE','UPDATE','DELETE','REVIEW','APPROVE','REJECT')", name="chk_audit_action"
        ),
        Index("ix_app_audit_entity", "entity_type", "entity_id"),
        Index("ix_app_audit_ts_brin", "performed_at", postgresql_using="brin"),
        {"schema": SCHEMA},
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
