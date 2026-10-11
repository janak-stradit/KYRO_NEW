"""watchlist identifiers — passport, national ID, tax, registration and IMO numbers on list entries

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-11

UK OFSI entries are backfilled from the rows already kept in raw_data. OFAC and
UN entries need the source files parsed again, so every source's last file
hash is cleared: the next list refresh re-reads each file even if unchanged.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"


def upgrade() -> None:
    import json

    from app.services.watchlist_adapters.uk_ofsi import _build_header_map, row_identifiers

    op.add_column("watchlist_entities", sa.Column("identifiers", postgresql.JSONB), schema=SCHEMA)
    op.add_column("watchlist_entities", sa.Column("identifier_values", postgresql.ARRAY(sa.Text)), schema=SCHEMA)

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        f"SELECT e.id, e.raw_data FROM {SCHEMA}.watchlist_entities e "
        f"JOIN {SCHEMA}.watchlist_sources s ON s.id = e.source_id WHERE s.code LIKE 'UK%' AND e.raw_data ? 'rows'"
    )).fetchall()
    update = sa.text(
        f"UPDATE {SCHEMA}.watchlist_entities SET identifiers = CAST(:identifiers AS jsonb), identifier_values = :values WHERE id = :id"
    )
    for row in rows:
        group = row.raw_data.get("rows") or []
        if not group:
            continue
        found = row_identifiers(group, _build_header_map(list(group[0].keys())))
        if found:
            bind.execute(update, {"id": row.id, "identifiers": json.dumps(found),
                                  "values": sorted({i["normalized"] for i in found})})

    op.execute(f"CREATE INDEX ix_watchlist_identifier_values ON {SCHEMA}.watchlist_entities USING gin (identifier_values)")
    op.execute(f"UPDATE {SCHEMA}.watchlist_sources SET last_file_hash = NULL")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_watchlist_identifier_values")
    op.drop_column("watchlist_entities", "identifier_values", schema=SCHEMA)
    op.drop_column("watchlist_entities", "identifiers", schema=SCHEMA)
