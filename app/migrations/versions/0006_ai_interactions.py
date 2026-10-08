"""ai interactions — audit log of every call through the AI gateway (Phase 11.0)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "ai_interactions",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("feature", sa.String(50), nullable=False),
        sa.Column("prompt_id", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.Integer, nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_redacted", sa.Text, nullable=False),
        sa.Column("output_text", sa.Text),
        sa.Column("output_json", JSONB),
        sa.Column("redaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("entity_id", UUID),
        sa.Column("requested_by", UUID),
        sa.Column("human_decision", sa.String(20)),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('SUCCESS', 'ERROR', 'DISABLED')", name="chk_ai_interaction_status"),
        sa.CheckConstraint(
            "human_decision IS NULL OR human_decision IN ('ACCEPTED', 'EDITED', 'REJECTED')",
            name="chk_ai_interaction_decision",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_ai_interactions_feature", "ai_interactions", ["feature"], schema=SCHEMA)
    op.create_index("ix_app_ai_interactions_entity_id", "ai_interactions", ["entity_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_app_ai_interactions_entity_id", table_name="ai_interactions", schema=SCHEMA)
    op.drop_index("ix_app_ai_interactions_feature", table_name="ai_interactions", schema=SCHEMA)
    op.drop_table("ai_interactions", schema=SCHEMA)
