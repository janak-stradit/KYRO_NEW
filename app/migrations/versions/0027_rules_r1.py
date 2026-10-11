"""rules engine R1 — exchange rates, base-currency amounts, alert provenance

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-11

Adds the tables and columns only; base-currency amounts for existing transactions are filled by
fx_service.backfill_amount_base (task fx_tasks.backfill_amount_base) once rates are loaded.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "fx_rates",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("rate_date", sa.Date, nullable=False, index=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_to_base", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("rate_date", "currency", name="uq_fx_rate_date_currency"),
        schema=SCHEMA,
    )
    op.add_column("transactions", sa.Column("amount_base", sa.Numeric(18, 2)), schema=SCHEMA)
    op.add_column("transactions", sa.Column("fx_rate", sa.Numeric(20, 10)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("rule_version", sa.String(64)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("parameters", postgresql.JSONB), schema=SCHEMA)
    op.add_column("alerts", sa.Column("evidence_transaction_ids", postgresql.ARRAY(UUID)), schema=SCHEMA)


def downgrade() -> None:
    for column in ("evidence_transaction_ids", "parameters", "rule_version"):
        op.drop_column("alerts", column, schema=SCHEMA)
    op.drop_column("transactions", "fx_rate", schema=SCHEMA)
    op.drop_column("transactions", "amount_base", schema=SCHEMA)
    op.drop_table("fx_rates", schema=SCHEMA)
