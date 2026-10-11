"""beneficial ownership — beneficial_owners table (UBO capture for
CORPORATE/FUND customers), pep_sanctions_screening.beneficial_owner_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "beneficial_owners",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("customer_id", UUID, sa.ForeignKey(f"{SCHEMA}.customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_type", sa.String(20), nullable=False, server_default="INDIVIDUAL"),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("nationality", sa.String(100)),
        sa.Column("country_of_residence", sa.String(100)),
        sa.Column("identification_type", sa.String(50)),
        sa.Column("identification_number", sa.String(100)),
        sa.Column("ownership_percentage", sa.Numeric(5, 2)),
        sa.Column("control_type", sa.String(20), nullable=False, server_default="OWNERSHIP"),
        sa.Column("control_description", sa.Text()),
        sa.Column("is_pep", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sanctions_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by", UUID),
        sa.Column("source", sa.String(50)),
        sa.Column("effective_from", sa.Date()),
        sa.Column("effective_to", sa.Date()),
        sa.Column("last_screened_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("owner_type IN ('INDIVIDUAL','ENTITY')", name="chk_ubo_owner_type"),
        sa.CheckConstraint(
            "control_type IN ('OWNERSHIP','VOTING_RIGHTS','SENIOR_MANAGEMENT','OTHER')", name="chk_ubo_control_type"
        ),
        sa.CheckConstraint(
            "verification_status IN ('PENDING','VERIFIED','REJECTED')", name="chk_ubo_verification_status"
        ),
        sa.CheckConstraint(
            "ownership_percentage IS NULL OR (ownership_percentage >= 0 AND ownership_percentage <= 100)",
            name="chk_ubo_ownership_pct",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_app_ubo_customer", "beneficial_owners", ["customer_id"], schema=SCHEMA)

    op.add_column(
        "pep_sanctions_screening",
        sa.Column("beneficial_owner_id", UUID, sa.ForeignKey(f"{SCHEMA}.beneficial_owners.id", ondelete="SET NULL")),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_app_screening_beneficial_owner", "pep_sanctions_screening", ["beneficial_owner_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_app_screening_beneficial_owner", table_name="pep_sanctions_screening", schema=SCHEMA)
    op.drop_column("pep_sanctions_screening", "beneficial_owner_id", schema=SCHEMA)

    op.drop_index("ix_app_ubo_customer", table_name="beneficial_owners", schema=SCHEMA)
    op.drop_table("beneficial_owners", schema=SCHEMA)
