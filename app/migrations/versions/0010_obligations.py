"""obligations — register of obligations extracted from regulatory sections (Phase 11.3 step 4)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "obligations",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "section_id", UUID, sa.ForeignKey(f"{SCHEMA}.regulatory_sections.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("section_ref", sa.String(100), nullable=False),
        sa.Column("section_version", sa.String(50), nullable=False),
        sa.Column("obligated_party", sa.String(255), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("deadline", sa.String(255)),
        sa.Column("condition", sa.Text),
        sa.Column("category", sa.String(30), nullable=False, server_default="OTHER"),
        sa.Column("source_quote", sa.Text),
        sa.Column("quote_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("extracted_by", sa.String(30), nullable=False),
        sa.Column("ai_interaction_id", UUID),
        sa.Column("reviewed_by", UUID),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'CONFIRMED', 'REJECTED', 'SUPERSEDED')", name="chk_obligation_status"
        ),
        sa.CheckConstraint(
            "category IN ('REPORTING', 'RECORDKEEPING', 'CUSTOMER_IDENTIFICATION', 'PROGRAM', 'MONITORING', 'OTHER')",
            name="chk_obligation_category",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_obligations_section_id", "obligations", ["section_id"], schema=SCHEMA)
    op.create_index("ix_app_obligations_section_ref", "obligations", ["section_ref"], schema=SCHEMA)
    op.create_index("ix_app_obligations_status", "obligations", ["status"], schema=SCHEMA)

    # Obligation reviews are written to the audit log
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_audit_entity_type",
        "audit_logs",
        "entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type = 'OBLIGATION'")
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_audit_entity_type",
        "audit_logs",
        "entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG')",
        schema=SCHEMA,
    )
    op.drop_index("ix_app_obligations_status", table_name="obligations", schema=SCHEMA)
    op.drop_index("ix_app_obligations_section_ref", table_name="obligations", schema=SCHEMA)
    op.drop_index("ix_app_obligations_section_id", table_name="obligations", schema=SCHEMA)
    op.drop_table("obligations", schema=SCHEMA)
