"""knowledge chunks — full-text retrieval store for the Compliance AI (Phase 11.0.5)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)

TSV_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(source_ref, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'B') || "
    "setweight(to_tsvector('english', content), 'C')"
)


def upgrade() -> None:
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("citation", sa.String(255)),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_tsv", postgresql.TSVECTOR, sa.Computed(TSV_EXPRESSION, persisted=True)),
        sa.Column("metadata", postgresql.JSONB),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('REGULATION', 'POLICY', 'DOCUMENT')", name="chk_knowledge_chunk_source_type"
        ),
        sa.UniqueConstraint("source_type", "source_ref", "version", "chunk_index", name="uq_knowledge_chunk_position"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_knowledge_chunks_tsv", "knowledge_chunks", ["content_tsv"], schema=SCHEMA, postgresql_using="gin"
    )
    op.create_index(
        "ix_app_knowledge_chunks_source", "knowledge_chunks", ["source_type", "source_ref"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_app_knowledge_chunks_source", table_name="knowledge_chunks", schema=SCHEMA)
    op.drop_index("ix_app_knowledge_chunks_tsv", table_name="knowledge_chunks", schema=SCHEMA)
    op.drop_table("knowledge_chunks", schema=SCHEMA)
