"""rules engine R2 — transaction direction and channel, counterparty details, code maps, segments, reconciliation

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-11

Existing transactions get a direction from their type (DEPOSIT → CREDIT, WITHDRAWAL → DEBIT; other types stay
unknown) and existing customers a segment from their customer type. Channel stays unknown for history: the rules
that need it skip, and count, rows without it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
CHANNELS = "('CASH','WIRE','ACH','CARD','CHEQUE','INTERNAL','CRYPTO','OTHER')"
SEGMENTS = "('RETAIL','HNW','SOLE_TRADER','SME','CORPORATE','FUND','MSB','NPO','CORRESPONDENT')"


def upgrade() -> None:
    for name, column in (
        ("direction", sa.String(10)), ("channel", sa.String(20)), ("counterparty_account", sa.String(100)),
        ("counterparty_bank_bic", sa.String(11)), ("counterparty_country", sa.String(100)), ("branch_id", sa.String(50)),
        ("depositor_name", sa.String(255)), ("reference", sa.String(100)), ("source_code", sa.String(50)),
    ):
        op.add_column("transactions", sa.Column(name, column), schema=SCHEMA)
    op.create_check_constraint("chk_transaction_direction", "transactions", "direction IS NULL OR direction IN ('CREDIT','DEBIT')", schema=SCHEMA)
    op.create_check_constraint("chk_transaction_channel", "transactions", f"channel IS NULL OR channel IN {CHANNELS}", schema=SCHEMA)
    op.execute(f"UPDATE {SCHEMA}.transactions SET direction = 'CREDIT' WHERE direction IS NULL AND transaction_type = 'DEPOSIT'")
    op.execute(f"UPDATE {SCHEMA}.transactions SET direction = 'DEBIT' WHERE direction IS NULL AND transaction_type = 'WITHDRAWAL'")
    op.create_index("ix_app_txn_source_reference", "transactions", ["source_system", "reference"], schema=SCHEMA)

    op.add_column("customers", sa.Column("segment", sa.String(20)), schema=SCHEMA)
    op.create_check_constraint("chk_customer_segment", "customers", f"segment IS NULL OR segment IN {SEGMENTS}", schema=SCHEMA)
    op.execute(f"""UPDATE {SCHEMA}.customers SET segment = CASE customer_type
        WHEN 'INDIVIDUAL' THEN 'RETAIL' WHEN 'CORPORATE' THEN 'CORPORATE' WHEN 'FUND' THEN 'FUND' END
        WHERE segment IS NULL""")

    op.create_table(
        "transaction_code_maps",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_system", sa.String(100), nullable=False),
        sa.Column("source_code", sa.String(50), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10)),
        sa.Column("channel", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("proposed_by", UUID),
        sa.Column("proposed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_notes", sa.Text),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','REJECTED','RETIRED')", name="chk_code_map_status"),
        sa.CheckConstraint("transaction_type IN ('DEPOSIT','WITHDRAWAL','TRANSFER','FX','TRADE')", name="chk_code_map_type"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('CREDIT','DEBIT')", name="chk_code_map_direction"),
        sa.CheckConstraint(f"channel IS NULL OR channel IN {CHANNELS}", name="chk_code_map_channel"),
        schema=SCHEMA,
    )
    op.create_index("uq_code_map_active", "transaction_code_maps", ["source_system", "source_code"], unique=True,
                    schema=SCHEMA, postgresql_where=sa.text("status = 'ACTIVE'"))

    op.create_table(
        "data_reconciliations",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("business_date", sa.Date, index=True),
        sa.Column("feed_run_id", UUID),
        sa.Column("received_count", sa.Integer),
        sa.Column("received_amount", sa.Numeric(20, 2)),
        sa.Column("stored_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stored_amount", sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("evaluated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_existing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("balanced", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("issues", postgresql.JSONB),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('FEED_LOAD', 'DAILY_SOURCE')", name="chk_reconciliation_kind"),
        schema=SCHEMA,
    )

    op.create_table(
        "customer_expected_activity",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("monthly_credit_value", sa.Numeric(18, 2)),
        sa.Column("monthly_debit_value", sa.Numeric(18, 2)),
        sa.Column("monthly_transaction_count", sa.Integer),
        sa.Column("cash_share_percent", sa.Integer),
        sa.Column("countries", postgresql.JSONB),
        sa.Column("purpose", sa.Text),
        sa.Column("source", sa.String(30)),
        sa.Column("recorded_by", UUID),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("customer_expected_activity", schema=SCHEMA)
    op.drop_table("data_reconciliations", schema=SCHEMA)
    op.drop_index("uq_code_map_active", table_name="transaction_code_maps", schema=SCHEMA)
    op.drop_table("transaction_code_maps", schema=SCHEMA)
    op.drop_constraint("chk_customer_segment", "customers", schema=SCHEMA, type_="check")
    op.drop_column("customers", "segment", schema=SCHEMA)
    op.drop_index("ix_app_txn_source_reference", table_name="transactions", schema=SCHEMA)
    op.drop_constraint("chk_transaction_channel", "transactions", schema=SCHEMA, type_="check")
    op.drop_constraint("chk_transaction_direction", "transactions", schema=SCHEMA, type_="check")
    for name in ("source_code", "reference", "depositor_name", "branch_id", "counterparty_country", "counterparty_bank_bic",
                 "counterparty_account", "channel", "direction"):
        op.drop_column("transactions", name, schema=SCHEMA)
