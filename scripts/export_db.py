"""
scripts/export_db.py — Export every row of the KYRO database in $DATABASE_URL
(users, customers, accounts, transactions, alerts, cases, rule settings ...)
to one file that deploy/restore_data.sh loads into the deployed server.

Only the data is exported: the server builds its tables with the same Alembic
migrations, and the file records which migration the data belongs to so the
restore can refuse a server that is on a different one.

Not exported: uploaded document files (var/documents) and trained models
(models/); they are files on disk, not database rows.

Usage (run_kyro.bat export does this for a local install):
    python scripts/export_db.py [output.sql.gz]
"""
from __future__ import annotations

import glob
import gzip
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

SCHEMA = "app"
HEADER = "-- kyro-data-export"
# Lines a newer pg_dump writes that an older server or psql does not accept
_SKIP_PREFIXES = ("SET transaction_timeout", "\\restrict", "\\unrestrict")


def _pg_dump() -> str | None:
    found = shutil.which("pg_dump")
    if found:
        return found
    candidates = sorted(glob.glob(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PostgreSQL", "*", "bin", "pg_dump.exe")))
    return candidates[-1] if candidates else None


def main() -> int:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("[!] DATABASE_URL is not set.")
        return 1
    url = make_url(raw)
    pg_dump = _pg_dump()
    if pg_dump is None:
        print("[!] pg_dump was not found. Install the PostgreSQL command line tools or add them to PATH.")
        return 1

    engine = create_engine(raw)
    with engine.connect() as conn:
        version = conn.execute(text(f"SELECT version_num FROM {SCHEMA}.alembic_version")).scalar()
        counts = {
            table: conn.execute(text(f'SELECT count(*) FROM {SCHEMA}."{table}"')).scalar()
            for table in ("users", "customers", "accounts", "transactions", "alerts")
        }
    engine.dispose()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join("var", "export", f"kyro_data_{version}_{stamp}.sql.gz")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    command = [
        pg_dump, "--data-only", f"--schema={SCHEMA}", f"--exclude-table-data={SCHEMA}.alembic_version",
        "--no-owner", "--no-privileges", "--encoding=UTF8",
        "-h", url.host or "localhost", "-p", str(url.port or 5432), "-U", url.username or "postgres", "-d", url.database,
    ]
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        with gzip.open(out, "wb") as f:
            f.write(f"{HEADER} alembic={version} created={stamp}\n".encode())
            for line in process.stdout:
                if not line.startswith(tuple(p.encode() for p in _SKIP_PREFIXES)):
                    f.write(line)
        errors = process.stderr.read().decode(errors="replace").strip()
        if process.wait() != 0:
            raise RuntimeError(errors or "pg_dump failed")
    except Exception as exc:
        process.kill()
        if os.path.exists(out):
            os.remove(out)
        print(f"[!] Export failed: {exc}")
        return 1
    if errors:
        print(errors)  # e.g. a warning about tables that reference each other

    print(f"Exported {', '.join(f'{n:,} {t}' for t, n in counts.items())} (migration {version})")
    print(f"  -> {out}  ({os.path.getsize(out) / 1024 / 1024:.1f} MB)")
    print("This file holds personal data and password hashes: copy it only to the server, and delete it afterwards.")
    print("Next: see 'Copy a database to the server' in deploy/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
