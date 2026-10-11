"""auto assignment — teams, their members and the rules that route new alerts to them

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-12

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        "team_members",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID, sa.ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", UUID, sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("available", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_assigned_at", sa.DateTime(timezone=True)),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        schema=SCHEMA,
    )
    op.create_table(
        "assignment_rules",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("team_id", UUID, sa.ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("conditions", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.add_column("alerts", sa.Column("team_id", UUID), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("alerts", "team_id", schema=SCHEMA)
    op.drop_table("assignment_rules", schema=SCHEMA)
    op.drop_table("team_members", schema=SCHEMA)
    op.drop_table("teams", schema=SCHEMA)
