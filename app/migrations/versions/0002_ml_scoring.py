"""ml scoring — ml_scores table, alert feedback columns, widened action check

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-14

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "ml_scores",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("transaction_id", UUID, sa.ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_scorer_version", sa.Integer()),
        sa.Column("anomaly_classifier_version", sa.Integer()),
        sa.Column("isolation_detector_version", sa.Integer()),
        sa.Column("is_candidate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rf_risk_score", sa.Float()),
        sa.Column("anomaly_probability", sa.Float()),
        sa.Column("isolation_score", sa.Float()),
        sa.Column("combined_score", sa.Float(), nullable=False),
        sa.Column("anomaly_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("explanation", JSONB),
        sa.Column("features", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("combined_score >= 0 AND combined_score <= 100", name="chk_ml_score_range"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_ml_score_txn", "ml_scores", ["transaction_id"], schema=SCHEMA)

    op.add_column("alerts", sa.Column("is_false_positive", sa.Boolean(), nullable=True), schema=SCHEMA)
    op.add_column("alerts", sa.Column("ml_version", sa.String(20), nullable=True), schema=SCHEMA)

    op.drop_constraint("chk_alert_recommended_action", "alerts", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_alert_recommended_action",
        "alerts",
        "recommended_action IS NULL OR recommended_action IN "
        "('REVIEW','ENHANCED_DUE_DILIGENCE','SAR','CLOSE','BATCH_REVIEW','IMMEDIATE_REVIEW')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("chk_alert_recommended_action", "alerts", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_alert_recommended_action",
        "alerts",
        "recommended_action IS NULL OR recommended_action IN ('REVIEW','ENHANCED_DUE_DILIGENCE','SAR','CLOSE')",
        schema=SCHEMA,
    )
    op.drop_column("alerts", "ml_version", schema=SCHEMA)
    op.drop_column("alerts", "is_false_positive", schema=SCHEMA)
    op.drop_table("ml_scores", schema=SCHEMA)
