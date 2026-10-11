"""
models/access_control.py — Access to SAR cases outside a user's role.

EmergencyAccessGrant: time-bound, read-only access to one case for someone
whose role cannot see it (typically an administrator investigating a fault).
It is requested with a reason, approved by a second person who may grant SAR
access, expires on its own and every use is audited.

RoleGrantRequest: giving someone a role that can see SAR cases is a second-
person decision too, so an administrator cannot hand SAR access to themselves
or to an account they control.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

GRANT_STATUSES = ("REQUESTED", "APPROVED", "REJECTED", "REVOKED")
ROLE_REQUEST_STATUSES = ("REQUESTED", "APPROVED", "REJECTED", "CANCELLED")


class EmergencyAccessGrant(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "emergency_access_grants"
    __table_args__ = (
        CheckConstraint(f"status IN {GRANT_STATUSES}", name="chk_emergency_access_status"),
        CheckConstraint("duration_minutes > 0", name="chk_emergency_access_duration"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Not a foreign key: requesting access must not reveal whether the case exists
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoleGrantRequest(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "role_grant_requests"
    __table_args__ = (
        CheckConstraint(f"status IN {ROLE_REQUEST_STATUSES}", name="chk_role_grant_status"),
        {"schema": SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_role: Mapped[str] = mapped_column(String(50), nullable=False)
    to_role: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTED")
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
