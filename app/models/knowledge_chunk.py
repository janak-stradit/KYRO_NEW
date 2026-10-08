"""
models/knowledge_chunk.py — Retrieval store for the Compliance AI (Phase 11.0.5).

One row per chunk of a regulation section, internal policy or uploaded
document. Every chunk keeps what is needed to cite it (source reference,
version, citation) so AI answers can point at the exact text they used.

Search is PostgreSQL full-text for now (`content_tsv`); an embedding column
for hybrid retrieval is added once the embeddings provider is decided
(docs/plans/COMPLIANCE_AI_PLAN.md §9.2).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Computed, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SCHEMA, UUIDPrimaryKeyMixin

KNOWLEDGE_SOURCE_TYPES = ("REGULATION", "POLICY", "DOCUMENT")

# Source reference and title outrank body text, so "Rule 3310" finds the rule itself first
TSV_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(source_ref, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'B') || "
    "setweight(to_tsvector('english', content), 'C')"
)


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        CheckConstraint(f"source_type IN {KNOWLEDGE_SOURCE_TYPES}", name="chk_knowledge_chunk_source_type"),
        UniqueConstraint("source_type", "source_ref", "version", "chunk_index", name="uq_knowledge_chunk_position"),
        Index("ix_app_knowledge_chunks_tsv", "content_tsv", postgresql_using="gin"),
        Index("ix_app_knowledge_chunks_source", "source_type", "source_ref"),
        {"schema": SCHEMA},
    )

    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "31 CFR 1023.320"
    version: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. effective date
    title: Mapped[str | None] = mapped_column(String(500))
    citation: Mapped[str | None] = mapped_column(String(255))  # section / page within the source
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed(TSV_EXPRESSION, persisted=True))
    meta: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
