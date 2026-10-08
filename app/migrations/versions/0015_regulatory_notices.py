"""regulatory notices — Federal Register rules and proposed rules for loaded CFR parts (Phase 11.5)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "regulatory_notices",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("document_number", sa.String(50), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("notice_type", sa.String(30), nullable=False),
        sa.Column("action", sa.Text),
        sa.Column("abstract", sa.Text),
        sa.Column("agencies", JSONB, nullable=False, server_default="[]"),
        sa.Column("publication_date", sa.Date, nullable=False),
        sa.Column("effective_on", sa.Date),
        sa.Column("comments_close_on", sa.Date),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("matched_parts", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("assessment_notes", sa.Text),
        sa.Column("assessed_by", UUID),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('NEW', 'ACTION_REQUIRED', 'NO_ACTION', 'CLOSED')", name="chk_regulatory_notice_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_regulatory_notices_publication_date", "regulatory_notices", ["publication_date"], schema=SCHEMA
    )
    op.create_index("ix_app_regulatory_notices_status", "regulatory_notices", ["status"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_app_regulatory_notices_status", table_name="regulatory_notices", schema=SCHEMA)
    op.drop_index("ix_app_regulatory_notices_publication_date", table_name="regulatory_notices", schema=SCHEMA)
    op.drop_table("regulatory_notices", schema=SCHEMA)
