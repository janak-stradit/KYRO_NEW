#!/usr/bin/env bash
# ============================================================
# KYRO — production deploy script.
# Runs ON THE EC2 HOST (invoked over SSH by .github/workflows/deploy.yml).
# Usage: deploy.sh <image-tag>
# ============================================================
set -euo pipefail

IMAGE_TAG="${1:?usage: deploy.sh <image-tag>}"
APP_DIR="/opt/kyro"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

cd "$APP_DIR"

echo "==> Pulling latest compose/deploy config from git"
git fetch origin main
git reset --hard origin/main

echo "==> Logging in to ECR"
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$ECR_REGISTRY"

export IMAGE_TAG ECR_REGISTRY

echo "==> Pulling images (tag: $IMAGE_TAG)"
$COMPOSE pull api frontend celery_worker celery_beat pipeline

echo "==> Running database migrations"
$COMPOSE run --rm api alembic upgrade head

echo "==> Starting stack"
$COMPOSE up -d --remove-orphans postgres redis api frontend celery_worker celery_beat

echo "==> Waiting for API health check"
healthy=false
for _ in $(seq 1 10); do
  if curl -sf http://localhost/api/v1/health > /dev/null; then
    healthy=true
    break
  fi
  sleep 3
done

if [ "$healthy" != "true" ]; then
  echo "!! API failed health check after deploy — check 'docker compose logs api'" >&2
  exit 1
fi

echo "==> Pruning old images"
docker image prune -f

echo "==> Deploy complete (tag: $IMAGE_TAG)"
