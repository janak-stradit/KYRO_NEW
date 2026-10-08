"""
models/feed.py — Data-feed field mapping (Phase 11.4 step 4).

FeedMapping: a saved answer to "which column of this client's file is which
KYRO field". FeedRun: one check or load of a file with a mapping, kept so
every bulk load can be traced to the file and the person who ran it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin

FEED_TARGETS = ("CUSTOMERS", "ACCOUNTS", "TRANSACTIONS")


class FeedMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "feed_mappings"
    __table_args__ = (
        CheckConstraint(f"target IN {FEED_TARGETS}", name="chk_feed_mapping_target"),
        {"schema": SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)  # KYRO field -> source column
    date_day_first: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FeedRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "feed_runs"
    __table_args__ = ({"schema": SCHEMA},)

    mapping_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.feed_mappings.id", ondelete="SET NULL")
    )
    target: Mapped[str] = mapped_column(String(20), nullable=False)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)  # as used for this run
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped_existing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)  # first errors, for the record
    run_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
