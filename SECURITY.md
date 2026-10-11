# Security

KYRO processes financial PII and AML investigation data. This document is
the production security checklist and records which items are enforced
automatically and which still need a manual sign-off.

## Reporting a vulnerability

Do not open a public GitHub issue. Email the maintainers privately with
reproduction steps and affected versions. We aim to acknowledge reports
within 2 business days.

## Automated gates (CI)

| Control | Where | Fails the build when |
|---|---|---|
| Secret scanning (gitleaks, full history) | `.github/workflows/security.yml` → `secret-scan` | A credential, key, or token is found in any commit |
| Dependency vulnerability scanning (pip-audit) | `.github/workflows/security.yml` → `dependency-scan` | Any pinned Python dependency has a known CVE |
| API test suite | `.github/workflows/deploy.yml` → `test` | Includes CORS and rate-limit tests (`tests/api/test_http_hardening.py`) |

The security workflow runs on every pull request, on pushes to `main` /
`kyrodatacollection`, and weekly. Make both jobs **required status checks**
in the GitHub branch protection rules so a red gate blocks the merge.

## Built-in application controls

| Control | Config | Default |
|---|---|---|
| CORS allow-list (`*` is ignored) | `CORS_ALLOWED_ORIGINS` (comma-separated) | `http://localhost:3000,http://127.0.0.1:3000` |
| Global per-IP rate limit | `RATE_LIMIT_DEFAULT` | `300/minute` |
| Login brute-force limit | `RATE_LIMIT_LOGIN` | `10/minute` |
| Shared limiter storage | `RATE_LIMIT_STORAGE_URI` | in-memory (set to Redis in prod) |
| Kill switch (tests only) | `RATE_LIMIT_ENABLED` | `true` |

The bundled frontend calls the API same-origin via nginx (`/api/` proxy),
so production needs **no** CORS entries. Only add origins for a separately
hosted client.

Rate limiting is a stopgap until a WAF (e.g. AWS WAF in front of an ALB)
is in place — see README Phase 8.6.

## Pre-production checklist (manual)

- [ ] `SECRET_KEY` set to `openssl rand -hex 32` output, supplied via GitHub
      environment secrets — never committed
- [ ] Demo users (`admin`/`admin123`, `analyst`/`kyro123`,
      `compliance`/`kyro123`, seeded in `app/main.py`) disabled or
      passwords rotated
- [ ] HTTPS via Let's Encrypt (`deploy/init-letsencrypt.sh`)
- [ ] Host firewall / security group allows only 80 and 443 publicly;
      the API port (`API_HOST_PORT`, default 8010) is **not** reachable
      from the internet — the API trusts `X-Forwarded-For` for rate limiting
- [ ] Postgres/Redis not published to the host (`docker-compose.prod.yml`)
- [ ] `RATE_LIMIT_STORAGE_URI` points at Redis
- [ ] Automated database backups configured and restore tested
- [ ] ElevenLabs API usage/quotas monitored

## Known gaps

Tracked in README §2.6 and Phase 8: secrets manager integration, PII
field-level encryption, MFA, tamper-evident audit log, WAF, finer RBAC.
