#!/usr/bin/env bash
# run.sh — Bring up the KYRO Risk Assessment stack (Postgres, Redis, API,
# Celery worker/beat, pgAdmin) and apply the app/ schema migrations.
#
# Usage:
#   ./run.sh              # build, start everything, run migrations
#   ./run.sh down         # stop and remove containers
#   ./run.sh logs [svc]   # follow logs (all services, or one)
#   ./run.sh migrate      # (re)apply app/ alembic migrations only
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

COMPOSE="docker compose"

case "${1:-up}" in
  down)
    $COMPOSE down
    exit 0
    ;;
  logs)
    $COMPOSE logs -f "${2:-}"
    exit 0
    ;;
  migrate)
    $COMPOSE run --rm api alembic upgrade head
    exit 0
    ;;
  up) ;;
  *)
    echo "Usage: $0 [up|down|logs [service]|migrate]" >&2
    exit 1
    ;;
esac

if [ ! -f .env ]; then
  echo "No .env found — creating one from .env.example"
  cp .env.example .env
fi

# Docker Compose parses .env natively; for our own use (the summary below)
# pull just the two values we need rather than `source`-ing the whole file,
# since unquoted values with spaces/inline comments aren't valid bash.
env_var() { grep "^$1=" .env | head -1 | cut -d= -f2- | sed 's/#.*//' | xargs; }
API_HOST_PORT="$(env_var API_HOST_PORT)"
REDIS_HOST_PORT="$(env_var REDIS_HOST_PORT)"

# The container's non-root `kyro` user's UID often won't match the host
# user that owns this bind-mounted dir, so a plain host-created directory
# can end up unwritable from inside the container. World-writable is fine
# here — it's just local model artifacts, not sensitive data.
mkdir -p models
chmod 777 models

echo "==> Starting Postgres + Redis"
$COMPOSE up -d postgres redis

echo "==> Waiting for Postgres to be healthy"
until [ "$(docker inspect -f '{{.State.Health.Status}}' kyro_postgres 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "==> Building API image and applying app/ schema migrations"
$COMPOSE build api
$COMPOSE run --rm api alembic upgrade head

echo "==> Starting API, Celery worker/beat, pgAdmin"
$COMPOSE up -d api celery_worker celery_beat pgadmin

cat <<EOF

KYRO stack is up:
  API docs   -> http://localhost:${API_HOST_PORT:-8000}/docs
  pgAdmin    -> http://localhost:5050
  Postgres   -> localhost:5434
  Redis      -> localhost:${REDIS_HOST_PORT:-6380}

Run './run.sh logs api' to tail the API, or './run.sh down' to stop everything.
EOF
