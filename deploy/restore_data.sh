#!/usr/bin/env bash
# ============================================================
# KYRO — load a database export into this server's database.
# Runs ON THE SERVER, from the app directory (/opt/kyro).
#
# The file comes from scripts/export_db.py (run_kyro.bat export) and holds
# every row of the source database: users, customers, accounts,
# transactions, alerts, cases, rule settings.
#
# EVERYTHING in this server's database is REPLACED by the file's contents.
# A backup is written to ./backups first, and the load is one transaction:
# if any part of it fails, the server's data is left exactly as it was.
#
# Usage: deploy/restore_data.sh <kyro_data_....sql.gz> [--yes]
# ============================================================
set -euo pipefail

DUMP="${1:?usage: restore_data.sh <export-file.sql.gz> [--yes]}"
ASSUME_YES="${2:-}"
PG_CONTAINER="${PG_CONTAINER:-kyro_postgres}"
APP_CONTAINERS="kyro_api kyro_celery_worker kyro_celery_beat"

[ -f "$DUMP" ] || { echo "!! No such file: $DUMP" >&2; exit 1; }

psql_db() {  # psql inside the postgres container, as the database's own user
  docker exec -i "$PG_CONTAINER" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh "$@"
}

header="$(gunzip -c "$DUMP" | head -n 1 || true)"
case "$header" in
  "-- kyro-data-export "*) ;;
  *) echo "!! $DUMP is not a KYRO data export (made by scripts/export_db.py)" >&2; exit 1 ;;
esac
dump_version="$(echo "$header" | sed -n 's/.*alembic=\([^ ]*\).*/\1/p')"
server_version="$(psql_db -Atc 'SELECT version_num FROM app.alembic_version')"

echo "==> Export is for migration $dump_version; this server is on migration $server_version"
if [ "$dump_version" != "$server_version" ]; then
  echo "!! They must match. Deploy the same version of the code that the export was made from" >&2
  echo "   (so its migrations run here), then run this again." >&2
  exit 1
fi

echo "==> This server now holds:"
psql_db -Atc "SELECT '    ' || count(*) || ' users' FROM app.users UNION ALL SELECT '    ' || count(*) || ' customers' FROM app.customers UNION ALL SELECT '    ' || count(*) || ' transactions' FROM app.transactions"
if [ "$ASSUME_YES" != "--yes" ]; then
  read -r -p "Replace ALL of it with the contents of $DUMP? Type 'replace' to continue: " answer
  [ "$answer" = "replace" ] || { echo "Nothing was changed."; exit 1; }
fi

mkdir -p backups
backup="backups/kyro_before_restore_$(date -u +%Y%m%d_%H%M%S).sql.gz"
echo "==> Backing up the current database to $backup"
umask 077
docker exec "$PG_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema=app --no-owner --no-privileges' | gzip > "$backup"

echo "==> Stopping the application while the data is replaced"
# shellcheck disable=SC2086
docker stop $APP_CONTAINERS > /dev/null 2>&1 || true
restart() {
  echo "==> Starting the application"
  # shellcheck disable=SC2086
  docker start $APP_CONTAINERS > /dev/null 2>&1 || true
}
trap restart EXIT

echo "==> Loading $DUMP"
{
  echo "BEGIN;"
  # Rows are loaded table by table; foreign keys are checked by the source database, not again here
  echo "SET session_replication_role = replica;"
  cat <<'SQL'
DO $$
DECLARE tables text;
BEGIN
  SELECT string_agg(format('%I.%I', schemaname, tablename), ', ') INTO tables
    FROM pg_tables WHERE schemaname = 'app' AND tablename <> 'alembic_version';
  EXECUTE 'TRUNCATE ' || tables || ' RESTART IDENTITY CASCADE';
END $$;
SQL
  gunzip -c "$DUMP"
  echo "COMMIT;"
} | psql_db -q > /dev/null

echo "==> Loaded. This server now holds:"
psql_db -Atc "SELECT '    ' || count(*) || ' users' FROM app.users UNION ALL SELECT '    ' || count(*) || ' customers' FROM app.customers UNION ALL SELECT '    ' || count(*) || ' transactions' FROM app.transactions"
echo "==> Done. The previous contents (tables and rows) are kept in $backup"
