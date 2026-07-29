#!/usr/bin/env bash
# ============================================================
# KYRO — one-time HTTPS bootstrap.
# Run ONCE, manually, on the EC2 instance from /opt/kyro:
#   ./deploy/init-letsencrypt.sh <domain> <email>
# Example (free sslip.io hostname, no domain purchase needed):
#   ./deploy/init-letsencrypt.sh 100-56-205-0.sslip.io you@example.com
#
# After this runs successfully, every future deploy.sh run keeps
# HTTPS working automatically (the cert lives in ./certbot/conf on
# the host, untouched by git). Renewal is a separate cron job --
# see deploy/README.md.
# ============================================================
set -euo pipefail

DOMAIN="${1:?usage: init-letsencrypt.sh <domain> <email>}"
EMAIL="${2:?usage: init-letsencrypt.sh <domain> <email>}"
: "${ECR_REGISTRY:?ECR_REGISTRY not set. Export it first, e.g.:
  export ECR_REGISTRY=<account-id>.dkr.ecr.<region>.amazonaws.com
(same value as the ECR_REGISTRY GitHub secret -- this script is run
manually, so it doesn't get it from CI like deploy.sh does)}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

mkdir -p certbot/conf/live/kyro certbot/www

echo "==> Creating a temporary self-signed cert so nginx can start"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout certbot/conf/live/kyro/privkey.pem \
  -out certbot/conf/live/kyro/fullchain.pem \
  -subj "/CN=$DOMAIN"

echo "==> Starting frontend with the temporary cert"
$COMPOSE up -d frontend

echo "==> Requesting the real certificate from Let's Encrypt"
rm -rf certbot/conf/live/kyro certbot/conf/archive/kyro certbot/conf/renewal/kyro.conf
$COMPOSE --profile certbot run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email \
  --cert-name kyro

echo "==> Reloading nginx with the real certificate"
$COMPOSE exec frontend nginx -s reload

echo "==> Done. Visit https://$DOMAIN"
