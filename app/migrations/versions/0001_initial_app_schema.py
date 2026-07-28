"""initial app schema — users, customers, accounts, transactions, alerts, audit

Revision ID: 0001
Revises:
Create Date: 2026-07-14

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
INET = postgresql.INET


def _uuid_pk() -> sa.Column:
    return sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True)


def upgrade() -> None:
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="ANALYST"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_login", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('ANALYST','COMPLIANCE_OFFICER','ADMIN')", name="chk_user_role"),
        sa.UniqueConstraint("username", name="uq_app_user_username"),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
        schema=SCHEMA,
    )

    op.create_table(
        "customers",
        _uuid_pk(),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50)),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("country", sa.String(100)),
        sa.Column("residency_country", sa.String(100)),
        sa.Column("kyc_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("kyc_last_review", sa.DateTime(timezone=True)),
        sa.Column("pep_flag", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sanctions_flag", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("adverse_media_flag", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="LOW"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customer_type", sa.String(50)),
        sa.Column("customer_metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="chk_customer_risk_score"),
        sa.CheckConstraint("kyc_status IN ('PENDING','VERIFIED','REJECTED','UNDER_REVIEW')", name="chk_customer_kyc_status"),
        sa.CheckConstraint("risk_level IN ('LOW','MEDIUM','HIGH')", name="chk_customer_risk_level"),
        sa.CheckConstraint("customer_type IN ('INDIVIDUAL','CORPORATE','FUND')", name="chk_customer_type"),
        sa.UniqueConstraint("email", name="uq_app_customer_email"),
        schema=SCHEMA,
    )

    op.create_table(
        "customer_risk_profiles",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_category", sa.String(50)),
        sa.Column("risk_factor", sa.String(255)),
        sa.Column("risk_weight", sa.Numeric(5, 2)),
        sa.Column("assessed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assessed_by", sa.String(50), nullable=False, server_default="SYSTEM"),
        sa.CheckConstraint(
            "risk_category IN ('GEOGRAPHIC','PRODUCT','CHANNEL','BEHAVIORAL')", name="chk_risk_profile_category"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_riskprofile_customer", "customer_risk_profiles", ["customer_id"], schema=SCHEMA)

    op.create_table(
        "kyc_reviews",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_type", sa.String(50)),
        sa.Column("review_status", sa.String(50), nullable=False, server_default="SCHEDULED"),
        sa.Column("scheduled_date", sa.Date()),
        sa.Column("completed_date", sa.DateTime(timezone=True)),
        sa.Column("findings", sa.Text()),
        sa.Column("risk_level_after", sa.String(20)),
        sa.Column("reviewed_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("review_type IN ('PERIODIC','TRIGGERED','ADHOC')", name="chk_kyc_review_type"),
        sa.CheckConstraint(
            "review_status IN ('SCHEDULED','IN_PROGRESS','COMPLETED','OVERDUE')", name="chk_kyc_review_status"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_kyc_review_customer", "kyc_reviews", ["customer_id"], schema=SCHEMA)

    op.create_table(
        "pep_sanctions_screening",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("screening_type", sa.String(50)),
        sa.Column("match_status", sa.String(50)),
        sa.Column("match_details", JSONB),
        sa.Column("screened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("screened_by", sa.String(50), nullable=False, server_default="SYSTEM"),
        sa.Column("resolution", sa.String(50)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID),
        sa.CheckConstraint("screening_type IN ('PEP','SANCTIONS','ADVERSE_MEDIA')", name="chk_screening_type"),
        sa.CheckConstraint(
            "match_status IN ('NO_MATCH','POTENTIAL_MATCH','CONFIRMED_MATCH')", name="chk_screening_match_status"
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ('CLEARED','ESCALATED','CONFIRMED')", name="chk_screening_resolution"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_screening_customer", "pep_sanctions_screening", ["customer_id"], schema=SCHEMA)

    op.create_table(
        "accounts",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_type", sa.String(50)),
        sa.Column("account_status", sa.String(50), nullable=False, server_default="ACTIVE"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("opened_date", sa.Date()),
        sa.Column("account_metadata", JSONB),
        sa.Column("risk_flags", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("account_type IN ('CHECKING','SAVINGS','INVESTMENT','TRADING')", name="chk_account_type"),
        sa.CheckConstraint("account_status IN ('ACTIVE','SUSPENDED','CLOSED','FROZEN')", name="chk_account_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_app_account_customer", "accounts", ["customer_id"], schema=SCHEMA)
    op.create_index("ix_app_account_status", "accounts", ["account_status"], schema=SCHEMA)

    op.create_table(
        "account_metadata",
        _uuid_pk(),
        sa.Column("account_id", UUID, sa.ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meta_key", sa.String(100)),
        sa.Column("meta_value", sa.Text()),
        sa.Column("meta_type", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "meta_type IS NULL OR meta_type IN ('STRING','NUMBER','BOOLEAN','JSON')", name="chk_account_meta_type"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_account_meta_account", "account_metadata", ["account_id"], schema=SCHEMA)

    op.create_table(
        "account_balances",
        _uuid_pk(),
        sa.Column("account_id", UUID, sa.ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("balance", sa.Numeric(18, 2)),
        sa.Column("available_balance", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_app_account_balance_account", "account_balances", ["account_id"], schema=SCHEMA)

    op.create_table(
        "transactions",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID, sa.ForeignKey(f"{SCHEMA}.accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_type", sa.String(50)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("meta_counterparty", sa.String(255)),
        sa.Column("meta_counterparty_type", sa.String(50)),
        sa.Column("meta_location", sa.String(255)),
        sa.Column("meta_country", sa.String(100)),
        sa.Column("meta_country_code", sa.String(3)),
        sa.Column("meta_destination_country", sa.String(100)),
        sa.Column("meta_origin_country", sa.String(100)),
        sa.Column("meta_source", sa.String(100)),
        sa.Column("risk_flags", JSONB),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_system", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="chk_transaction_amount_positive"),
        sa.CheckConstraint(
            "transaction_type IS NULL OR transaction_type IN ('DEPOSIT','WITHDRAWAL','TRANSFER','FX','TRADE')",
            name="chk_transaction_type",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_txn_customer", "transactions", ["customer_id"], schema=SCHEMA)
    op.create_index("ix_app_txn_account", "transactions", ["account_id"], schema=SCHEMA)
    op.create_index("ix_app_txn_date_brin", "transactions", ["transaction_date"], schema=SCHEMA, postgresql_using="brin")
    op.create_index("ix_app_txn_risk_flags_gin", "transactions", ["risk_flags"], schema=SCHEMA, postgresql_using="gin")

    op.create_table(
        "transaction_counterparties",
        _uuid_pk(),
        sa.Column("transaction_id", UUID, sa.ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_name", sa.String(255)),
        sa.Column("counterparty_type", sa.String(50)),
        sa.Column("counterparty_country", sa.String(100)),
        sa.Column("counterparty_account", sa.String(100)),
        sa.Column("bank_name", sa.String(255)),
        sa.Column("bank_country", sa.String(100)),
        sa.Column("relationship_to_customer", sa.String(100)),
        schema=SCHEMA,
    )
    op.create_index("ix_app_txn_cp_txn", "transaction_counterparties", ["transaction_id"], schema=SCHEMA)

    op.create_table(
        "transaction_risk_flags",
        _uuid_pk(),
        sa.Column("transaction_id", UUID, sa.ForeignKey(f"{SCHEMA}.transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flag_type", sa.String(100)),
        sa.Column("flag_description", sa.Text()),
        sa.Column("flag_severity", sa.String(20)),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("triggered_by", sa.String(50), nullable=False, server_default="RULES_ENGINE"),
        sa.CheckConstraint(
            "flag_severity IS NULL OR flag_severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="chk_txn_flag_severity"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_txn_flag_txn", "transaction_risk_flags", ["transaction_id"], schema=SCHEMA)

    op.create_table(
        "alerts",
        _uuid_pk(),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(100)),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 2)),
        sa.Column("triggered_rules", JSONB),
        sa.Column("ml_explanation", JSONB),
        sa.Column("recommended_action", sa.String(100)),
        sa.Column("status", sa.String(50), nullable=False, server_default="OPEN"),
        sa.Column("assigned_to", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID),
        sa.Column("resolution_notes", sa.Text()),
        sa.CheckConstraint(
            "recommended_action IS NULL OR recommended_action IN ('REVIEW','ENHANCED_DUE_DILIGENCE','SAR','CLOSE')",
            name="chk_alert_recommended_action",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ASSIGNED','IN_REVIEW','RESOLVED','ESCALATED')", name="chk_alert_status"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_alert_customer", "alerts", ["customer_id"], schema=SCHEMA)
    op.create_index("ix_app_alert_status", "alerts", ["status"], schema=SCHEMA)

    op.create_table(
        "audit_logs",
        _uuid_pk(),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID, nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("performed_by", UUID),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("old_values", JSONB),
        sa.Column("new_values", JSONB),
        sa.Column("ip_address", INET),
        sa.Column("user_agent", sa.Text()),
        sa.CheckConstraint("entity_type IN ('CUSTOMER','ACCOUNT','TRANSACTION','ALERT')", name="chk_audit_entity_type"),
        sa.CheckConstraint(
            "action IN ('CREATE','UPDATE','DELETE','REVIEW','APPROVE','REJECT')", name="chk_audit_action"
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_audit_entity", "audit_logs", ["entity_type", "entity_id"], schema=SCHEMA)
    op.create_index("ix_app_audit_ts_brin", "audit_logs", ["performed_at"], schema=SCHEMA, postgresql_using="brin")


def downgrade() -> None:
    op.drop_table("audit_logs", schema=SCHEMA)
    op.drop_table("alerts", schema=SCHEMA)
    op.drop_table("transaction_risk_flags", schema=SCHEMA)
    op.drop_table("transaction_counterparties", schema=SCHEMA)
    op.drop_table("transactions", schema=SCHEMA)
    op.drop_table("account_balances", schema=SCHEMA)
    op.drop_table("account_metadata", schema=SCHEMA)
    op.drop_table("accounts", schema=SCHEMA)
    op.drop_table("pep_sanctions_screening", schema=SCHEMA)
    op.drop_table("kyc_reviews", schema=SCHEMA)
    op.drop_table("customer_risk_profiles", schema=SCHEMA)
    op.drop_table("customers", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
    op.execute(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
