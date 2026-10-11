"""watchlist alias and phonetic search — search list entries by alias and by sound; transliterated names

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-11

Backfills every existing entry: normalized_name is recomputed (non-Latin names
are now transliterated rather than dropped) and alias_text / phonetic_text are
filled, so screening finds them without waiting for the next list refresh.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "app"
_BATCH = 2000


def upgrade() -> None:
    from app.services.screening_service import normalize_name, search_columns

    op.add_column("watchlist_entities", sa.Column("alias_text", sa.Text), schema=SCHEMA)
    op.add_column("watchlist_entities", sa.Column("phonetic_text", sa.Text), schema=SCHEMA)

    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, primary_name, aka_names FROM {SCHEMA}.watchlist_entities")).fetchall()
    update = sa.text(
        f"UPDATE {SCHEMA}.watchlist_entities SET normalized_name = :normalized, alias_text = :alias_text, "
        "phonetic_text = :phonetic_text WHERE id = :id"
    )
    for start in range(0, len(rows), _BATCH):
        bind.execute(update, [
            {"id": row.id, "normalized": normalize_name(row.primary_name), **search_columns(row.primary_name, row.aka_names)}
            for row in rows[start:start + _BATCH]
        ])

    op.execute(f"CREATE INDEX ix_watchlist_alias_trgm ON {SCHEMA}.watchlist_entities USING gin (alias_text gin_trgm_ops)")
    op.execute(f"CREATE INDEX ix_watchlist_phonetic_trgm ON {SCHEMA}.watchlist_entities USING gin (phonetic_text gin_trgm_ops)")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_watchlist_phonetic_trgm")
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_watchlist_alias_trgm")
    op.drop_column("watchlist_entities", "phonetic_text", schema=SCHEMA)
    op.drop_column("watchlist_entities", "alias_text", schema=SCHEMA)
