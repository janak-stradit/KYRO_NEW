"""SAR narratives — every draft and edit of a case's narrative, kept as a version

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "sar_narratives",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id", UUID, sa.ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(30)),
        sa.Column("ai_interaction_id", UUID),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("alert_id", "version", name="uq_sar_narrative_version"),
        sa.CheckConstraint("source IN ('AI_DRAFT', 'EDITED')", name="chk_sar_narrative_source"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("sar_narratives", schema=SCHEMA)
