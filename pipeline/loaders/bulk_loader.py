"""
loaders/bulk_loader.py — PostgreSQL data loading layer.
Supports: COPY (fastest), bulk INSERT, UPSERT (ON CONFLICT), SCD Type 1 & 2.
Implements: transaction management, rollback, checkpointing, retry.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from sqlalchemy import Table, MetaData, text, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pipeline.core.database import get_engine, get_psycopg_conn, with_retry
from pipeline.core.exceptions import ConstraintViolationError, DuplicateKeyError

logger = logging.getLogger(__name__)


# ── COPY-based bulk load (fastest method) ─────────────────────

def bulk_copy(
    df: pd.DataFrame,
    schema: str,
    table: str,
    conninfo: str,
) -> int:
    """
    Use PostgreSQL COPY FROM STDIN for maximum insert throughput.
    Significantly faster than INSERT for large batches (>10k rows).

    Returns: number of rows copied.
    """
    if df.empty:
        return 0
    cols = list(df.columns)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, header=False, na_rep="\\N")
    csv_buffer.seek(0)

    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            col_list = ", ".join(f'"{c}"' for c in cols)
            copy_sql = f'COPY "{schema}"."{table}" ({col_list}) FROM STDIN WITH (FORMAT CSV, NULL \'\\N\')'
            with cur.copy(copy_sql) as copy:
                copy.write(csv_buffer.read())
        conn.commit()

    logger.info("COPY loaded %d rows → %s.%s", len(df), schema, table)
    return len(df)


# ── Schema reflection helper (cached per table) ───────────────

_TABLE_SCHEMA_CACHE: dict[str, set[str]] = {}


def _get_table_columns(engine, schema: str, table: str) -> set[str]:
    """Return the set of column names for a table, cached in memory."""
    key = f"{schema}.{table}"
    if key not in _TABLE_SCHEMA_CACHE:
        try:
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns(table, schema=schema)}
            _TABLE_SCHEMA_CACHE[key] = cols
            logger.debug("Reflected schema for %s: %d columns", key, len(cols))
        except Exception as exc:
            logger.error("Cannot reflect schema for %s: %s", key, exc)
            raise
    return _TABLE_SCHEMA_CACHE[key]


# ── UPSERT (ON CONFLICT DO UPDATE) ───────────────────────────

import psycopg
from sqlalchemy.exc import OperationalError, PendingRollbackError

@with_retry(max_retries=3, backoff=2.0, exceptions=(OperationalError, PendingRollbackError, psycopg.OperationalError))
def upsert_dataframe(
    df: pd.DataFrame,
    schema: str,
    table: str,
    conflict_columns: list[str],
    update_columns: list[str] | None = None,
    batch_size: int = 1000,
    config: dict | None = None,
    on_conflict: str = "update",          # "update" | "nothing"
) -> tuple[int, int]:
    """
    Upsert DataFrame rows using PostgreSQL ON CONFLICT.

    Args:
        conflict_columns: Columns forming the unique constraint (conflict target).
                          All columns must be NOT NULL for partitioned tables.
        update_columns:   Columns to update on conflict; None = update all non-PK cols.
        batch_size:       Rows per transaction batch.
        on_conflict:      "update" → ON CONFLICT DO UPDATE SET ...
                          "nothing" → ON CONFLICT DO NOTHING (idempotent, no update)

    Returns:
        (inserted_count, updated_count)  — PostgreSQL rowcount tracks both as "affected".
    """
    if df is None or df.empty:
        return 0, 0

    engine = get_engine(config)
    inserted = updated = 0

    # ── Reflect table schema once (schema drift protection) ───
    try:
        valid_cols = _get_table_columns(engine, schema, table)
    except Exception as exc:
        logger.error("Table %s.%s not found in database: %s", schema, table, exc)
        raise

    # Filter DataFrame to only columns that exist in the DB
    df_cols = [c for c in df.columns if c in valid_cols]
    if not df_cols:
        logger.error("No matching columns between DataFrame and %s.%s — skipping", schema, table)
        return 0, 0
    df_filtered = df[df_cols].copy()

    # Validate that all conflict columns are present
    missing_conflict = [c for c in conflict_columns if c not in df_filtered.columns]
    if missing_conflict:
        logger.error(
            "Conflict columns %s not in DataFrame for %s.%s — cannot upsert",
            missing_conflict, schema, table,
        )
        raise ValueError(f"Conflict columns {missing_conflict} missing from DataFrame")

    # Convert to records first
    records = df_filtered.to_dict(orient="records")

    import pandas as pd
    def _clean_val(val):
        if isinstance(val, (list, tuple)):
            return [_clean_val(v) for v in val]
        if isinstance(val, dict):
            return {k: _clean_val(v) for k, v in val.items()}
        
        # At this point, val is a scalar. Safe to use pd.isna
        if pd.isna(val):
            return None
        return val

    cleaned_records = []
    for r in records:
        cleaned_records.append({k: _clean_val(v) for k, v in r.items()})
    records = cleaned_records

    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        try:
            with engine.begin() as conn:
                meta = MetaData()
                tbl = Table(table, meta, schema=schema, autoload_with=engine)

                stmt = pg_insert(tbl).values(batch)

                if on_conflict == "nothing":
                    if conflict_columns:
                        final_stmt = stmt.on_conflict_do_nothing(index_elements=conflict_columns)
                    else:
                        # No specific constraint — ignore any conflict (safe for append-only tables)
                        final_stmt = stmt.on_conflict_do_nothing()
                else:
                    update_cols = update_columns or [
                        c.name for c in tbl.columns
                        if c.name not in conflict_columns and c.name not in ("id", "created_at")
                    ]
                    final_stmt = stmt.on_conflict_do_update(
                        index_elements=conflict_columns,
                        set_={c: stmt.excluded[c] for c in update_cols if c in df_filtered.columns},
                    )

                result = conn.execute(final_stmt)
                inserted += result.rowcount

        except Exception as exc:
            logger.error(
                "Upsert batch %d/%d failed for %s.%s: %s",
                i // batch_size + 1, (len(records) - 1) // batch_size + 1,
                schema, table, exc,
            )
            raise

    logger.info("Upsert complete: ~%d rows affected → %s.%s", inserted, schema, table)
    return inserted, updated


# ── Incremental / Checkpoint Loading ─────────────────────────

def get_last_checkpoint(
    schema: str, table: str, watermark_col: str, engine=None, config: dict | None = None
) -> Any:
    """Return the MAX watermark value from target table for incremental loading."""
    eng = engine or get_engine(config)
    with eng.connect() as conn:
        result = conn.execute(
            text(f'SELECT MAX("{watermark_col}") FROM "{schema}"."{table}"')
        )
        row = result.fetchone()
        return row[0] if row else None


def save_checkpoint(execution_id: str, checkpoint_value: Any, config: dict | None = None) -> None:
    """Persist checkpoint to metadata.pipeline_executions for resume capability."""
    eng = get_engine(config)
    with eng.begin() as conn:
        conn.execute(
            text("""
                UPDATE metadata.pipeline_executions
                SET config_snapshot = jsonb_set(
                    COALESCE(config_snapshot, '{}'::jsonb),
                    '{checkpoint}',
                    :val::jsonb
                )
                WHERE execution_id = :eid
            """),
            {"val": json.dumps({"value": str(checkpoint_value), "saved_at": datetime.now(timezone.utc).isoformat()}),
             "eid": execution_id},
        )


# ── SCD Type 2 ────────────────────────────────────────────────

def scd2_merge(
    new_df: pd.DataFrame,
    schema: str,
    table: str,
    business_key: str,
    compare_columns: list[str],
    engine=None,
    config: dict | None = None,
) -> dict:
    """
    Slowly Changing Dimension Type 2 merge.
    - Unchanged records: no action.
    - Changed records: expire old row (set wh_valid_to, wh_is_current=False), insert new.
    - New records: insert directly.

    Returns: {"inserted": n, "expired": n}
    """
    eng = engine or get_engine(config)
    inserted = expired = 0
    now = datetime.now(timezone.utc)

    with eng.begin() as conn:
        # Load current active records
        existing = pd.read_sql(
            f'SELECT * FROM "{schema}"."{table}" WHERE wh_is_current = TRUE',
            conn,
        )
        if existing.empty:
            # First load — insert all
            new_df["wh_valid_from"] = now
            new_df["wh_valid_to"] = None
            new_df["wh_is_current"] = True
            new_df.to_sql(table, conn, schema=schema, if_exists="append", index=False, method="multi")
            inserted = len(new_df)
            logger.info("SCD2 first load: inserted %d rows into %s.%s", inserted, schema, table)
            return {"inserted": inserted, "expired": 0}

        # Merge logic
        existing_keyed = existing.set_index(business_key)
        for _, new_row in new_df.iterrows():
            key = new_row[business_key]
            if key not in existing_keyed.index:
                # New record
                new_row["wh_valid_from"] = now
                new_row["wh_valid_to"] = None
                new_row["wh_is_current"] = True
                pd.DataFrame([new_row]).to_sql(table, conn, schema=schema, if_exists="append", index=False, method="multi")
                inserted += 1
            else:
                old_row = existing_keyed.loc[key]
                changed = any(
                    str(new_row.get(c)) != str(old_row.get(c, ""))
                    for c in compare_columns if c in new_row.index
                )
                if changed:
                    # Expire old
                    conn.execute(
                        text(f'UPDATE "{schema}"."{table}" SET wh_valid_to=:now, wh_is_current=FALSE WHERE "{business_key}"=:key AND wh_is_current=TRUE'),
                        {"now": now, "key": key},
                    )
                    expired += 1
                    # Insert new version
                    new_row["wh_valid_from"] = now
                    new_row["wh_valid_to"] = None
                    new_row["wh_is_current"] = True
                    pd.DataFrame([new_row]).to_sql(table, conn, schema=schema, if_exists="append", index=False, method="multi")
                    inserted += 1

    logger.info("SCD2 merge [%s.%s]: inserted=%d expired=%d", schema, table, inserted, expired)
    return {"inserted": inserted, "expired": expired}
