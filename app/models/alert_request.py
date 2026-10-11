"""
models/alert_request.py — Requests for information raised on a case.

Records that documents or an explanation were asked for, from whom, by when,
and whether the answer arrived, so an open request is visible to whoever
picks the case up next.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

REQUEST_STATUSES = ("OPEN", "RECEIVED", "CANCELLED")


class AlertRequest(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "alert_requests"
    __table_args__ = (
        CheckConstraint(f"status IN {REQUEST_STATUSES}", name="chk_alert_request_status"),
        {"schema": SCHEMA},
    )

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_from: Mapped[str] = mapped_column(String(150), nullable=False)  # e.g. "Customer", "Relationship manager"
    subject: Mapped[str] = mapped_column(Text, nullable=False)  # what was asked for
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    response_note: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
