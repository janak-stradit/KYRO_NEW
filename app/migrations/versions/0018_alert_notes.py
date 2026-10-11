"""alert notes — investigation notes on a case

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "alert_notes",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("alert_id", UUID, sa.ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_app_alert_notes_alert_id", "alert_notes", ["alert_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_app_alert_notes_alert_id", table_name="alert_notes", schema=SCHEMA)
    op.drop_table("alert_notes", schema=SCHEMA)
