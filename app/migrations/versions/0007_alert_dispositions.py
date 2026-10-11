"""alert dispositions — outcome + reason codes on alerts (Phase 11.2 step 0)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column("alerts", sa.Column("resolution_outcome", sa.String(30)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("resolution_reasons", postgresql.JSONB), schema=SCHEMA)
    op.add_column("alerts", sa.Column("sar_reference", sa.String(100)), schema=SCHEMA)
    op.create_check_constraint(
        "chk_alert_resolution_outcome",
        "alerts",
        "resolution_outcome IS NULL OR resolution_outcome IN "
        "('SAR_FILED','ESCALATED','TRUE_POSITIVE_NO_SAR','FALSE_POSITIVE')",
        schema=SCHEMA,
    )
    op.create_index("ix_app_alerts_resolution_outcome", "alerts", ["resolution_outcome"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_app_alerts_resolution_outcome", table_name="alerts", schema=SCHEMA)
    op.drop_constraint("chk_alert_resolution_outcome", "alerts", schema=SCHEMA)
    op.drop_column("alerts", "sar_reference", schema=SCHEMA)
    op.drop_column("alerts", "resolution_reasons", schema=SCHEMA)
    op.drop_column("alerts", "resolution_outcome", schema=SCHEMA)
