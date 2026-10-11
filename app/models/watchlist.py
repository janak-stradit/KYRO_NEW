"""
models/watchlist.py — Sanctions/PEP watchlist sources, normalized entities,
and ingestion run history (Phase 4.1: real, scheduled, auditable screening).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin


class WatchlistSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "watchlist_sources"
    __table_args__ = (
        CheckConstraint(
            "list_category IN ('SANCTIONS','PEP','ADVERSE_MEDIA')", name="chk_watchlist_source_category"
        ),
        {"schema": SCHEMA},
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    list_category: Mapped[str] = mapped_column(String(20), nullable=False, default="SANCTIONS")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_file_hash: Mapped[str | None] = mapped_column(String(64))


class WatchlistEntity(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "watchlist_entities"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('INDIVIDUAL','ENTITY','VESSEL','OTHER')", name="chk_watchlist_entity_type"
        ),
        UniqueConstraint("source_id", "external_id", name="uq_watchlist_entity_source_external_id"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.watchlist_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, default="INDIVIDUAL")
    primary_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    aka_names: Mapped[list | None] = mapped_column(JSONB)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    place_of_birth: Mapped[str | None] = mapped_column(String(255))
    nationalities: Mapped[list | None] = mapped_column(JSONB)
    addresses: Mapped[list | None] = mapped_column(JSONB)
    programs: Mapped[list | None] = mapped_column(JSONB)
    remarks: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    list_version: Mapped[str | None] = mapped_column(String(100))
    # Candidate search (screening_service.py): normalised aliases, and how every name sounds
    alias_text: Mapped[str | None] = mapped_column(Text)
    phonetic_text: Mapped[str | None] = mapped_column(Text)


class WatchlistIngestionRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "watchlist_ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','SUCCESS','FAILED','SKIPPED_UNCHANGED')", name="chk_ingestion_run_status"
        ),
        {"schema": SCHEMA},
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.watchlist_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_deactivated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
