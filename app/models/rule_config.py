"""
models/rule_config.py — DB-backed, jurisdiction-aware overrides for the
rules engine's thresholds (Phase 4.4). A row with jurisdiction='GLOBAL'
overrides the hardcoded default for every customer; a row with a specific
ISO country code overrides it only for customers in that jurisdiction.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, TimestampMixin, UUIDPrimaryKeyMixin

GLOBAL_JURISDICTION = "GLOBAL"


class RuleConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rule_configs"
    __table_args__ = (
        UniqueConstraint("key", "jurisdiction", name="uq_rule_config_key_jurisdiction"),
        {"schema": SCHEMA},
    )

    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, default=GLOBAL_JURISDICTION)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
