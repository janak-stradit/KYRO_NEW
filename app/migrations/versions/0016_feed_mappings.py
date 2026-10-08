"""feed mappings — saved column mappings and feed run history (Phase 11.4 step 4)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "feed_mappings",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("mapping", JSONB, nullable=False),
        sa.Column("date_day_first", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("target IN ('CUSTOMERS', 'ACCOUNTS', 'TRANSACTIONS')", name="chk_feed_mapping_target"),
        schema=SCHEMA,
    )
    op.create_table(
        "feed_runs",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("mapping_id", UUID, sa.ForeignKey(f"{SCHEMA}.feed_mappings.id", ondelete="SET NULL")),
        sa.Column("target", sa.String(20), nullable=False),
        sa.Column("mapping", JSONB, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("dry_run", sa.Boolean, nullable=False),
        sa.Column("rows_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_valid", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_loaded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_skipped_existing", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_invalid", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", JSONB),
        sa.Column("run_by", UUID),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("feed_runs", schema=SCHEMA)
    op.drop_table("feed_mappings", schema=SCHEMA)
