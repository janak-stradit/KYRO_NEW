"""
models/ai_interaction.py — One row per call through the AI gateway (Phase 11.0).

Stores what was asked (redacted), which prompt version and model answered,
the result, and, once an analyst acts on it, their decision, so every AI
output shown in KYRO can be traced and reproduced.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin

AI_STATUSES = ("SUCCESS", "ERROR", "DISABLED")
AI_DECISIONS = ("ACCEPTED", "EDITED", "REJECTED")


class AIInteraction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_interactions"
    __table_args__ = (
        CheckConstraint(f"status IN {AI_STATUSES}", name="chk_ai_interaction_status"),
        CheckConstraint(
            f"human_decision IS NULL OR human_decision IN {AI_DECISIONS}",
            name="chk_ai_interaction_decision",
        ),
        Index("ix_app_ai_interactions_feature", "feature"),
        Index("ix_app_ai_interactions_entity_id", "entity_id"),
        {"schema": SCHEMA},
    )

    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # What left KYRO (after redaction) and what came back (before re-identification)
    input_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)

    # What the output was about, and who asked
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # The human decision on the output
    human_decision: Mapped[str | None] = mapped_column(String(20))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
