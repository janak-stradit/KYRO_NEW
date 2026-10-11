"""
models/alert_note.py — Investigation notes on a case.

A note is written once and never edited or deleted, so the case file reads
the same to a reviewer or auditor as it did to the analyst who wrote it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class AlertNote(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "alert_notes"
    __table_args__ = ({"schema": SCHEMA},)

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
