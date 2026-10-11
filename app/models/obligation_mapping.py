"""
models/obligation_mapping.py — Which KYRO control meets which obligation
(Phase 11.4). Proposed by the AI or added by a reviewer; only CONFIRMED
mappings count as coverage.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin

MAPPING_STATUSES = ("PROPOSED", "CONFIRMED", "REJECTED")


class ObligationMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "obligation_mappings"
    __table_args__ = (
        CheckConstraint(f"status IN {MAPPING_STATUSES}", name="chk_obligation_mapping_status"),
        UniqueConstraint("obligation_id", "control_code", name="uq_obligation_mapping_control"),
        {"schema": SCHEMA},
    )

    obligation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.obligations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    control_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # control_catalogue code
    rationale: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROPOSED")
    proposed_by: Mapped[str] = mapped_column(String(30), nullable=False)  # provider name, or "user"
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
