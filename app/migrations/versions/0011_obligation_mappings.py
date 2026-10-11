"""obligation mappings — obligation → KYRO control (Phase 11.4)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
AUDIT_TYPES = "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION'"


def _set_audit_types(types: str) -> None:
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint("chk_audit_entity_type", "audit_logs", f"entity_type IN ({types})", schema=SCHEMA)


def upgrade() -> None:
    op.create_table(
        "obligation_mappings",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "obligation_id", UUID, sa.ForeignKey(f"{SCHEMA}.obligations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("control_code", sa.String(50), nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("proposed_by", sa.String(30), nullable=False),
        sa.Column("ai_interaction_id", UUID),
        sa.Column("reviewed_by", UUID),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')", name="chk_obligation_mapping_status"),
        sa.UniqueConstraint("obligation_id", "control_code", name="uq_obligation_mapping_control"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_obligation_mappings_obligation_id", "obligation_mappings", ["obligation_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_app_obligation_mappings_control_code", "obligation_mappings", ["control_code"], schema=SCHEMA
    )
    _set_audit_types(f"{AUDIT_TYPES},'OBLIGATION_MAPPING'")


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type = 'OBLIGATION_MAPPING'")
    _set_audit_types(AUDIT_TYPES)
    op.drop_index("ix_app_obligation_mappings_control_code", table_name="obligation_mappings", schema=SCHEMA)
    op.drop_index("ix_app_obligation_mappings_obligation_id", table_name="obligation_mappings", schema=SCHEMA)
    op.drop_table("obligation_mappings", schema=SCHEMA)
