"""audit teams — audit entries for teams and assignment rules

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-12

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
AUDIT_TYPES = (
    "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION','OBLIGATION_MAPPING',"
    "'REGULATORY_CHANGE','RULE_CONFIG_CHANGE','DOCUMENT','USER','SAR','EMERGENCY_ACCESS'"
)


def _check(expression: str) -> None:
    op.drop_constraint("chk_audit_entity_type", "audit_logs", schema=SCHEMA, type_="check")
    op.create_check_constraint("chk_audit_entity_type", "audit_logs", expression, schema=SCHEMA)


def upgrade() -> None:
    _check(f"entity_type IN ({AUDIT_TYPES},'TEAM','ASSIGNMENT_RULE')")


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type IN ('TEAM','ASSIGNMENT_RULE')")
    _check(f"entity_type IN ({AUDIT_TYPES})")
