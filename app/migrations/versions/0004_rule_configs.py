"""rule configs — DB-backed, jurisdiction-aware rule threshold overrides,
widen audit_logs.entity_type to allow RULE_CONFIG

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

# Mirrors the hardcoded fallback constants in app/services/rules_engine.py
# at the time this migration was written; editing a value here only changes
# the seeded starting point, not the engine's own fallback if this row is
# later deactivated.
SEED_ROWS = [
    {"key": "AMOUNT_THRESHOLD", "value": {"value": 10000}, "description": "Single-transaction amount above which R001 fires."},
    {"key": "VELOCITY_DAILY_LIMIT", "value": {"value": 5}, "description": "Transactions/day above which R002 fires."},
    {"key": "VELOCITY_HOURLY_LIMIT", "value": {"value": 3}, "description": "Transactions/hour above which R003 fires."},
    {"key": "RAPID_SUCCESSION_WINDOW_SECONDS", "value": {"value": 60}, "description": "Window for R010 rapid-succession detection."},
    {"key": "ALERT_THRESHOLD", "value": {"value": 50}, "description": "Combined risk score above which an alert is opened."},
    {"key": "EDD_THRESHOLD", "value": {"value": 75}, "description": "Combined risk score above which Enhanced Due Diligence is recommended."},
    {
        "key": "HIGH_RISK_COUNTRIES",
        "value": {"value": ["AF", "AFGHANISTAN", "IR", "IRAN", "KP", "MM", "MYANMAR", "NORTH KOREA", "SS", "SY", "SYRIA", "YE", "YEMEN"]},
        "description": "R004 high-risk/sanctioned jurisdiction list (FATF-style).",
    },
    {
        "key": "SEVERITY_WEIGHT",
        "value": {"value": {"LOW": 10, "MEDIUM": 25, "HIGH": 50, "CRITICAL": 90}},
        "description": "Points contributed per triggered-rule severity when scoring a transaction.",
    },
]


def upgrade() -> None:
    op.create_table(
        "rule_configs",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("jurisdiction", sa.String(10), nullable=False, server_default="GLOBAL"),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("key", "jurisdiction", name="uq_rule_config_key_jurisdiction"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_rule_config_key", "rule_configs", ["key"], schema=SCHEMA)

    rule_configs_table = sa.table(
        "rule_configs",
        sa.column("key", sa.String),
        sa.column("jurisdiction", sa.String),
        sa.column("value", JSONB),
        sa.column("description", sa.Text),
        schema=SCHEMA,
    )
    op.bulk_insert(
        rule_configs_table,
        [{"jurisdiction": "GLOBAL", **row} for row in SEED_ROWS],
    )

    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_audit_entity_type",
        "audit_logs",
        "entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_audit_entity_type",
        "audit_logs",
        "entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT')",
        schema=SCHEMA,
    )
    op.drop_index("ix_app_rule_config_key", table_name="rule_configs", schema=SCHEMA)
    op.drop_table("rule_configs", schema=SCHEMA)
