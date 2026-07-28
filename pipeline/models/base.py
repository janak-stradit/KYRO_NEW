"""
models/base.py — SQLAlchemy declarative base and UUID primary key mixin.
All ORM models inherit from these for consistent schema, audit columns, and PK strategy.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all KYRO pipeline models."""
    pass


class UUIDPrimaryKeyMixin:
    """Mixin that provides a UUID v4 primary key column named `id`."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
        comment="Surrogate UUID primary key",
    )


class TimestampMixin:
    """Mixin providing created_at / updated_at audit timestamp columns.
    updated_at is auto-set on every UPDATE via SQLAlchemy's onupdate hook.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp (UTC)",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Last update timestamp (UTC)",
    )


class SoftDeleteMixin:
    """Mixin supporting logical (soft) deletes via `is_deleted` flag."""

    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        index=True,
        comment="Soft delete flag; True = logically deleted",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when record was soft-deleted",
    )
