"""change management — regulatory_changes and rule_config_changes (Phase 11.5)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
AUDIT_TYPES = "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION','OBLIGATION_MAPPING'"


def _set_audit_types(types: str) -> None:
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint("chk_audit_entity_type", "audit_logs", f"entity_type IN ({types})", schema=SCHEMA)


def upgrade() -> None:
    op.create_table(
        "regulatory_changes",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "source_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("run_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_ingestion_runs.id", ondelete="SET NULL")),
        sa.Column("section_ref", sa.String(100), nullable=False),
        sa.Column("heading", sa.String(500)),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("old_section_id", UUID),
        sa.Column("new_section_id", UUID),
        sa.Column("old_version", sa.String(50)),
        sa.Column("new_version", sa.String(50)),
        sa.Column("affected", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("assessment_notes", sa.Text),
        sa.Column("assessed_by", UUID),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("change_type IN ('ADDED', 'AMENDED', 'REMOVED')", name="chk_regulatory_change_type"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ACTION_REQUIRED', 'NO_ACTION', 'CLOSED')", name="chk_regulatory_change_status"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_regulatory_changes_source_id", "regulatory_changes", ["source_id"], schema=SCHEMA)
    op.create_index("ix_app_regulatory_changes_status", "regulatory_changes", ["status"], schema=SCHEMA)

    op.create_table(
        "rule_config_changes",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("jurisdiction", sa.String(10), nullable=False, server_default="GLOBAL"),
        sa.Column("previous_value", JSONB, nullable=False),
        sa.Column("proposed_value", JSONB, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column(
            "regulatory_change_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_changes.id", ondelete="SET NULL")
        ),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("backtest", JSONB),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING_APPROVAL"),
        sa.Column("proposed_by", UUID, nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_by", UUID),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'ACTIVE', 'CANCELLED')",
            name="chk_rule_config_change_status",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_rule_config_changes_key", "rule_config_changes", ["key"], schema=SCHEMA)
    op.create_index("ix_app_rule_config_changes_status", "rule_config_changes", ["status"], schema=SCHEMA)

    _set_audit_types(f"{AUDIT_TYPES},'REGULATORY_CHANGE','RULE_CONFIG_CHANGE'")


def downgrade() -> None:
    op.execute(
        f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type IN ('REGULATORY_CHANGE', 'RULE_CONFIG_CHANGE')"
    )
    _set_audit_types(AUDIT_TYPES)
    op.drop_index("ix_app_rule_config_changes_status", table_name="rule_config_changes", schema=SCHEMA)
    op.drop_index("ix_app_rule_config_changes_key", table_name="rule_config_changes", schema=SCHEMA)
    op.drop_table("rule_config_changes", schema=SCHEMA)
    op.drop_index("ix_app_regulatory_changes_status", table_name="regulatory_changes", schema=SCHEMA)
    op.drop_index("ix_app_regulatory_changes_source_id", table_name="regulatory_changes", schema=SCHEMA)
    op.drop_table("regulatory_changes", schema=SCHEMA)
