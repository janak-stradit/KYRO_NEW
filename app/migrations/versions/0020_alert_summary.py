"""alert summary — the generated case summary kept on the alert

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column("alerts", sa.Column("summary", sa.Text), schema=SCHEMA)
    op.add_column("alerts", sa.Column("summary_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("summary_by", postgresql.UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("summary_provider", sa.String(30)), schema=SCHEMA)


def downgrade() -> None:
    for column in ("summary_provider", "summary_by", "summary_at", "summary"):
        op.drop_column("alerts", column, schema=SCHEMA)
