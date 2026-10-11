"""roles and case QA — wider role list, quality-check fields on alerts, USER audit entries

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-09

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
UUID = postgresql.UUID(as_uuid=True)
OLD_ROLES = "'ANALYST','COMPLIANCE_OFFICER','ADMIN'"
NEW_ROLES = (
    "'ADMIN','MLRO','TEAM_LEAD','L2_INVESTIGATOR','L1_ANALYST','KYC_ANALYST','QA_REVIEWER','RULES_OWNER',"
    "'AUDITOR','EXECUTIVE_VIEWER','COMPLIANCE_OFFICER','ANALYST'"
)
AUDIT_TYPES = (
    "'CUSTOMER','ACCOUNT','TRANSACTION','ALERT','RULE_CONFIG','OBLIGATION','OBLIGATION_MAPPING',"
    "'REGULATORY_CHANGE','RULE_CONFIG_CHANGE','DOCUMENT'"
)


def _check(name: str, table: str, expression: str) -> None:
    op.drop_constraint(name, table, schema=SCHEMA, type_="check")
    op.create_check_constraint(name, table, expression, schema=SCHEMA)


def upgrade() -> None:
    _check("chk_user_role", "users", f"role IN ({NEW_ROLES})")
    _check("chk_audit_entity_type", "audit_logs", f"entity_type IN ({AUDIT_TYPES},'USER')")

    op.add_column("alerts", sa.Column("qa_result", sa.String(10)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("qa_notes", sa.Text), schema=SCHEMA)
    op.add_column("alerts", sa.Column("qa_by", UUID), schema=SCHEMA)
    op.add_column("alerts", sa.Column("qa_at", sa.DateTime(timezone=True)), schema=SCHEMA)
    op.create_check_constraint(
        "chk_alert_qa_result", "alerts", "qa_result IS NULL OR qa_result IN ('PASS','FAIL')", schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_constraint("chk_alert_qa_result", "alerts", schema=SCHEMA, type_="check")
    for column in ("qa_at", "qa_by", "qa_notes", "qa_result"):
        op.drop_column("alerts", column, schema=SCHEMA)
    op.execute(f"DELETE FROM {SCHEMA}.audit_logs WHERE entity_type = 'USER'")
    _check("chk_audit_entity_type", "audit_logs", f"entity_type IN ({AUDIT_TYPES})")
    # Users on a role the old list does not know fall back to the least-privileged one
    op.execute(f"UPDATE {SCHEMA}.users SET role = 'ANALYST' WHERE role NOT IN ({OLD_ROLES})")
    _check("chk_user_role", "users", f"role IN ({OLD_ROLES})")
