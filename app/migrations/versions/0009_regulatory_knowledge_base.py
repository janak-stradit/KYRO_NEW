"""regulatory knowledge base — sources, ingestion runs, versioned sections (Phase 11.3)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

# US broker-dealer AML scope (docs/plans/COMPLIANCE_AI_PLAN.md §9.4). eCFR text
# is a US Government work in the public domain.
SOURCE_SEEDS = [
    {
        "code": "ECFR_31_1023",
        "name": "31 CFR Part 1023 — Rules for brokers or dealers in securities",
        "source_kind": "ECFR",
        "jurisdiction": "US",
        "config": {"title": 31, "part": "1023"},
    },
    {
        "code": "ECFR_31_1010",
        "name": "31 CFR Part 1010 — General provisions (Bank Secrecy Act)",
        "source_kind": "ECFR",
        "jurisdiction": "US",
        "config": {"title": 31, "part": "1010"},
    },
    {
        "code": "ECFR_17_240_17A8",
        "name": "17 CFR 240.17a-8 — Financial recordkeeping and reporting of currency and foreign transactions",
        "source_kind": "ECFR",
        "jurisdiction": "US",
        "config": {"title": 17, "part": "240", "section": "240.17a-8"},
    },
]


def upgrade() -> None:
    op.create_table(
        "regulatory_sources",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("jurisdiction", sa.String(10), nullable=False, server_default="US"),
        sa.Column("config", JSONB, nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_content_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_kind IN ('ECFR')", name="chk_regulatory_source_kind"),
        schema=SCHEMA,
    )

    op.create_table(
        "regulatory_ingestion_runs",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "source_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("as_of", sa.String(20)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("sections_seen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sections_added", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sections_changed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sections_removed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.CheckConstraint(
            "status IN ('PENDING','SUCCESS','FAILED','SKIPPED_UNCHANGED')", name="chk_regulatory_run_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_regulatory_ingestion_runs_source_id", "regulatory_ingestion_runs", ["source_id"], schema=SCHEMA
    )

    op.create_table(
        "regulatory_sections",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "source_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_ingestion_runs.id", ondelete="SET NULL")),
        sa.Column("section_ref", sa.String(100), nullable=False),
        sa.Column("heading", sa.String(500)),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("source_note", sa.Text),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_regulatory_sections_ref", "regulatory_sections", ["source_id", "section_ref"], schema=SCHEMA
    )
    op.create_index(
        "ix_app_regulatory_sections_is_current", "regulatory_sections", ["is_current"], schema=SCHEMA
    )

    sources_table = sa.table(
        "regulatory_sources",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("source_kind", sa.String),
        sa.column("jurisdiction", sa.String),
        sa.column("config", JSONB),
        schema=SCHEMA,
    )
    op.bulk_insert(sources_table, SOURCE_SEEDS)


def downgrade() -> None:
    op.drop_index("ix_app_regulatory_sections_is_current", table_name="regulatory_sections", schema=SCHEMA)
    op.drop_index("ix_app_regulatory_sections_ref", table_name="regulatory_sections", schema=SCHEMA)
    op.drop_table("regulatory_sections", schema=SCHEMA)
    op.drop_index(
        "ix_app_regulatory_ingestion_runs_source_id", table_name="regulatory_ingestion_runs", schema=SCHEMA
    )
    op.drop_table("regulatory_ingestion_runs", schema=SCHEMA)
    op.drop_table("regulatory_sources", schema=SCHEMA)
