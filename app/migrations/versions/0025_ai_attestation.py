"""AI attestation — an investigator's confirmation that an AI case summary was checked against the records

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-11

Narratives need no new column: a version saved by a person (source EDITED) is
saved with the same confirmation, enforced by the API.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"


def upgrade() -> None:
    op.add_column("alerts", sa.Column("summary_interaction_id", postgresql.UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("summary_attested_by", postgresql.UUID(as_uuid=True)), schema=SCHEMA)
    op.add_column("alerts", sa.Column("summary_attested_at", sa.DateTime(timezone=True)), schema=SCHEMA)


def downgrade() -> None:
    for column in ("summary_attested_at", "summary_attested_by", "summary_interaction_id"):
        op.drop_column("alerts", column, schema=SCHEMA)
