"""access control and deadlines — emergency access, approval of SAR-bearing roles, case and SAR clocks

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "emergency_access_grants",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("alert_id", UUID, nullable=False, index=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="REQUESTED"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_notes", sa.Text),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", UUID),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'REVOKED')", name="chk_emergency_access_status"),
        sa.CheckConstraint("duration_minutes > 0", name="chk_emergency_access_duration"),
        schema=SCHEMA,
    )
    op.create_table(
        "role_grant_requests",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("from_role", sa.String(50), nullable=False),
        sa.Column("to_role", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="REQUESTED"),
        sa.Column("requested_by", UUID, nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_notes", sa.Text),
        sa.CheckConstraint("status IN ('REQUESTED', 'APPROVED', 'REJECTED', 'CANCELLED')", name="chk_role_grant_status"),
        schema=SCHEMA,
    )
    op.add_column("alerts", sa.Column("detected_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("sla_days", sa.Integer), schema=SCHEMA)
    op.add_column("alerts", sa.Column("sar_candidate_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("sar_decision_days", sa.Integer), schema=SCHEMA)
    op.add_column("alerts", sa.Column("filing_due_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    # Existing alerts were detected when they were raised
    op.execute(f"UPDATE {SCHEMA}.alerts SET detected_at = created_at WHERE detected_at IS NULL")


def downgrade() -> None:
    for column in ("filing_due_at", "sar_decision_days", "sar_candidate_at", "sla_days", "detected_at"):
        op.drop_column("alerts", column, schema=SCHEMA)
    op.drop_table("role_grant_requests", schema=SCHEMA)
    op.drop_table("emergency_access_grants", schema=SCHEMA)
