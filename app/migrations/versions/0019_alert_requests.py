"""alert requests — requests for information raised on a case

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-10

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "alert_requests",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("alert_id", UUID, sa.ForeignKey(f"{SCHEMA}.alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_from", sa.String(150), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("response_note", sa.Text),
        sa.Column("requested_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_by", UUID),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('OPEN', 'RECEIVED', 'CANCELLED')", name="chk_alert_request_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_alert_requests_alert_id", "alert_requests", ["alert_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_app_alert_requests_alert_id", table_name="alert_requests", schema=SCHEMA)
    op.drop_table("alert_requests", schema=SCHEMA)
