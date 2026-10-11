"""SAR access audit — audit entries for opening a SAR-filed case and for emergency access

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-11

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
AUDIT_TYPES = (
    "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION','OBLIGATION_MAPPING',"
    "'REGULATORY_CHANGE','RULE_CONFIG_CHANGE','DOCUMENT','USER'"
)
AUDIT_ACTIONS = "'CREATE','UPDATE','DELETE','REVIEW','APPROVE','REJECT'"


def _check(name: str, table: str, expression: str) -> None:
    op.drop_constraint(name, table, schema=SCHEMA, type_="check")
    op.create_check_constraint(name, table, expression, schema=SCHEMA)


def upgrade() -> None:
    _check("chk_audit_entity_type", "audit_logs", f"entity_type IN ({AUDIT_TYPES},'SAR','EMERGENCY_ACCESS')")
    _check("chk_audit_action", "audit_logs", f"action IN ({AUDIT_ACTIONS},'VIEW')")


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type IN ('SAR','EMERGENCY_ACCESS') OR action = 'VIEW'")
    _check("chk_audit_action", "audit_logs", f"action IN ({AUDIT_ACTIONS})")
    _check("chk_audit_entity_type", "audit_logs", f"entity_type IN ({AUDIT_TYPES})")
