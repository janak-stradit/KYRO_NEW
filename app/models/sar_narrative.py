"""
models/sar_narrative.py — Versions of a case's SAR narrative.

Every draft, whether written by the model or edited by an investigator, is kept
as a new version; nothing is overwritten. Once a case is SAR-sensitive (a
potential SAR or a filed one) its narratives are visible only to roles with
"sar.view" (services/sar_confidentiality.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

NARRATIVE_SOURCES = ("AI_DRAFT", "EDITED")


class SarNarrative(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sar_narratives"
    __table_args__ = (
        UniqueConstraint("alert_id", "version", name="uq_sar_narrative_version"),
        CheckConstraint(f"source IN {NARRATIVE_SOURCES}", name="chk_sar_narrative_source"),
        {"schema": SCHEMA},
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(30))  # the model's provider, for AI drafts
    ai_interaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
