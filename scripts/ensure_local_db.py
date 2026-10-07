"""
scripts/ensure_local_db.py — Makes sure the database in $DATABASE_URL exists and
is usable before run_kyro.bat applies migrations (local, non-Docker runs).

Creates the database if it's missing (needs a role with CREATEDB, e.g. the
`postgres` superuser) and enables pg_trgm, which the screening migration needs.
Exit code 0 = ready, 1 = problem (message printed).
"""
from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


def main() -> int:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("[!] DATABASE_URL is not set.")
        return 1

    url = make_url(raw)
    if not url.database:
        print("[!] DATABASE_URL has no database name (e.g. .../kyro_aml).")
        return 1

    conninfo = dict(
        host=url.host or "localhost",
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        connect_timeout=5,
    )
    where = f"{conninfo['user']}@{conninfo['host']}:{conninfo['port']}"

    try:
        conn = psycopg.connect(dbname=url.database, autocommit=True, **conninfo)
    except psycopg.OperationalError as exc:
        if f'database "{url.database}" does not exist' not in str(exc):
            print(f"[!] Cannot connect to PostgreSQL as {where}: {str(exc).strip()}")
            print("    Check the PostgreSQL service is running and the URL in local.env is right.")
            return 1
        print(f"Database '{url.database}' not found - creating it...")
        try:
            with psycopg.connect(dbname="postgres", autocommit=True, **conninfo) as admin:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(url.database)))
        except psycopg.Error as create_exc:
            print(f"[!] Could not create database '{url.database}': {str(create_exc).strip()}")
            return 1
        conn = psycopg.connect(dbname=url.database, autocommit=True, **conninfo)

    with conn:
        try:
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        except psycopg.Error as exc:
            print(f"[!] Could not enable the pg_trgm extension: {str(exc).strip()}")
            return 1

    print(f"Database OK ({url.database} on {where}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
