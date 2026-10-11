"""
models/assignment.py — Automatic assignment of new alerts (services/assignment_service.py).

Team             a group of people who work the same kind of case
TeamMember       a user in a team; `available` is false while they are away
AssignmentRule   which alerts go to which team: checked in priority order, the
                 first rule whose conditions all match decides the team
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin


class Team(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "teams"
    __table_args__ = ({"schema": SCHEMA},)

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TeamMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"), {"schema": SCHEMA})

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # false while on leave
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # round-robin order
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AssignmentRule(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "assignment_rules"
    __table_args__ = ({"schema": SCHEMA},)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)  # lower is checked first
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # All given conditions must match; an empty set matches every alert (a catch-all):
    # {"alert_types": [...], "rules_any": ["R006", ...], "min_score": 80, "max_score": 100,
    #  "segments": [...], "countries": [...], "recommended_actions": [...]}
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
