"""watchlist screening — watchlist_sources/entities/ingestion_runs, screening
match columns, pg_trgm fuzzy-match index, customer.last_screened_at

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

SOURCE_SEEDS = [
    {
        "code": "OFAC_SDN",
        "name": "OFAC Specially Designated Nationals List",
        "list_category": "SANCTIONS",
        "url": "https://www.treasury.gov/ofac/downloads/sdn.xml",
    },
    {
        "code": "OFAC_CONSOLIDATED",
        "name": "OFAC Consolidated Non-SDN Sanctions List",
        "list_category": "SANCTIONS",
        "url": "https://www.treasury.gov/ofac/downloads/consolidated/consolidated.xml",
    },
    {
        "code": "UN_CONSOLIDATED",
        "name": "UN Security Council Consolidated Sanctions List",
        "list_category": "SANCTIONS",
        "url": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    },
    {
        "code": "UK_OFSI",
        "name": "UK OFSI Consolidated List of Financial Sanctions Targets",
        "list_category": "SANCTIONS",
        "url": "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv",
    },
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "watchlist_sources",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("list_category", sa.String(20), nullable=False, server_default="SANCTIONS"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_file_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "list_category IN ('SANCTIONS','PEP','ADVERSE_MEDIA')", name="chk_watchlist_source_category"
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "watchlist_entities",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_id", UUID, sa.ForeignKey(f"{SCHEMA}.watchlist_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False, server_default="INDIVIDUAL"),
        sa.Column("primary_name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("aka_names", JSONB),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("place_of_birth", sa.String(255)),
        sa.Column("nationalities", JSONB),
        sa.Column("addresses", JSONB),
        sa.Column("programs", JSONB),
        sa.Column("remarks", sa.Text()),
        sa.Column("raw_data", JSONB),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("list_version", sa.String(100)),
        sa.CheckConstraint(
            "entity_type IN ('INDIVIDUAL','ENTITY','VESSEL','OTHER')", name="chk_watchlist_entity_type"
        ),
        sa.UniqueConstraint("source_id", "external_id", name="uq_watchlist_entity_source_external_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_watchlist_entity_source", "watchlist_entities", ["source_id"], schema=SCHEMA)
    op.create_index("ix_app_watchlist_entity_active", "watchlist_entities", ["is_active"], schema=SCHEMA)
    op.execute(
        f"CREATE INDEX ix_app_watchlist_entity_name_trgm ON {SCHEMA}.watchlist_entities "
        f"USING gin (normalized_name gin_trgm_ops)"
    )

    op.create_table(
        "watchlist_ingestion_runs",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source_id", UUID, sa.ForeignKey(f"{SCHEMA}.watchlist_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("file_hash", sa.String(64)),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_deactivated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.CheckConstraint(
            "status IN ('PENDING','SUCCESS','FAILED','SKIPPED_UNCHANGED')", name="chk_ingestion_run_status"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_watchlist_run_source", "watchlist_ingestion_runs", ["source_id"], schema=SCHEMA)

    op.add_column("customers", sa.Column("last_screened_at", sa.DateTime(timezone=True)), schema=SCHEMA)

    op.add_column(
        "pep_sanctions_screening",
        sa.Column("watchlist_entity_id", UUID, sa.ForeignKey(f"{SCHEMA}.watchlist_entities.id", ondelete="SET NULL")),
        schema=SCHEMA,
    )
    op.add_column("pep_sanctions_screening", sa.Column("match_score", sa.Numeric(5, 2)), schema=SCHEMA)
    op.create_index(
        "ix_app_screening_watchlist_entity", "pep_sanctions_screening", ["watchlist_entity_id"], schema=SCHEMA
    )

    sources_table = sa.table(
        "watchlist_sources",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("list_category", sa.String),
        sa.column("url", sa.Text),
        schema=SCHEMA,
    )
    op.bulk_insert(sources_table, SOURCE_SEEDS)


def downgrade() -> None:
    op.drop_index("ix_app_screening_watchlist_entity", table_name="pep_sanctions_screening", schema=SCHEMA)
    op.drop_column("pep_sanctions_screening", "match_score", schema=SCHEMA)
    op.drop_column("pep_sanctions_screening", "watchlist_entity_id", schema=SCHEMA)
    op.drop_column("customers", "last_screened_at", schema=SCHEMA)

    op.drop_index("ix_app_watchlist_run_source", table_name="watchlist_ingestion_runs", schema=SCHEMA)
    op.drop_table("watchlist_ingestion_runs", schema=SCHEMA)

    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_app_watchlist_entity_name_trgm")
    op.drop_index("ix_app_watchlist_entity_active", table_name="watchlist_entities", schema=SCHEMA)
    op.drop_index("ix_app_watchlist_entity_source", table_name="watchlist_entities", schema=SCHEMA)
    op.drop_table("watchlist_entities", schema=SCHEMA)

    op.drop_table("watchlist_sources", schema=SCHEMA)
