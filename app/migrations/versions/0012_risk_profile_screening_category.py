"""risk profile categories — allow SCREENING factors (sanctions, PEP, adverse media)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-08

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
OLD = "'GEOGRAPHIC','PRODUCT','CHANNEL','BEHAVIORAL'"


def _set_categories(categories: str) -> None:
    op.drop_constraint("chk_risk_profile_category", "customer_risk_profiles", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "chk_risk_profile_category", "customer_risk_profiles", f"risk_category IN ({categories})", schema=SCHEMA
    )


def upgrade() -> None:
    _set_categories(f"{OLD},'SCREENING'")


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.customer_risk_profiles WHERE risk_category = 'SCREENING'")
    _set_categories(OLD)
