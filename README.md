# KYRO AML — Enterprise Readiness Plan

KYRO is an AML (Anti-Money Laundering) risk assessment platform for banks:
FastAPI backend, PostgreSQL, a Celery-driven ETL pipeline, a rules + ML
scoring engine, and a static analyst frontend. This document captures what
exists today, where it falls short of a bank-grade AML program, and the
prioritized plan to close the gap.

## 1. What's already built

| Area | Current implementation |
|---|---|
| **Data model** | `customers`, `accounts`, `transactions`, `alerts`, `kyc_reviews`, `pep_sanctions_screening`, `customer_risk_profiles`, `transaction_risk_flags`, `audit_log` (`app/models/`) |
| **Transaction rules engine** | 10 static rules R001–R010 — amount threshold, hourly/daily velocity, high-risk country, PEP, sanctions, new counterparty, weekend activity, round amount, rapid succession (`app/services/rules_engine.py`) |
| **ML scoring** | Risk scorer, anomaly classifier, isolation-forest detector, model registry with versioning, SHAP explainability, batch + real-time scorers, feedback-driven retraining (`app/ml/`) |
| **Alert routing** | ML score → log-only / batch-review / immediate-review by static thresholds (`app/services/alert_service.py`) |
| **Alert workflow** | Open → Assigned → In-Review → Resolved/Escalated, role-gated assign/resolve/escalate, SSE live alert stream (`app/routers/alerts.py`) |
| **KYC** | Manual/periodic/triggered review scheduling, PEP/sanctions/adverse-media screening table with match status + resolution (`app/routers/kyc.py`, `app/models/customer.py`) |
| **Audit trail** | `AuditLog` writes on create/update/review/approve/reject (`app/services/audit_service.py`) |
| **AuthN/Z** | JWT auth, 3 roles (ADMIN / ANALYST / COMPLIANCE_OFFICER), `require_role` dependency |
| **ETL pipeline** | Ingestion → cleaning → transformation → feature engineering → data quality checks → bulk load, with DLQ + reprocessing (`pipeline/`) |
| **Ops tooling** | Celery worker/beat, Redis, Dockerized stack, GitHub Actions → ECR, EC2 deploy script, Let's Encrypt HTTPS |
| **Frontend** | Dashboard, case review, behavioral patterns, periodic reviews, reports, Kyro AI chat assistant with ElevenLabs voice |

This is a credible **Phase 1–3 prototype**: the skeleton of every core AML
pillar exists. What's missing is the depth, governance, and hardening a
regulator or bank compliance function would actually require in production.

## 2. Gap analysis against a bank-grade AML program

### 2.1 Sanctions / PEP / Adverse Media screening — thin
- `HIGH_RISK_COUNTRIES` is a hardcoded 7-country set in code; `pep_flag` /
  `sanctions_flag` are booleans with no source-of-truth feed behind them.
- No real list ingestion (OFAC SDN, UN, EU, UK HMT, OFSI) or vendor
  integration (World-Check, Dow Jones, ComplyAdvantage, Moody's Orbis).
- No fuzzy/phonetic name matching (Jaro-Winkler, Soundex, transliteration) —
  today it's exact boolean flags only.
- No perpetual/ongoing monitoring — customers aren't re-screened when lists
  update, only at onboarding or manual trigger.

### 2.2 Transaction monitoring depth — rules are shallow
- No **structuring/smurfing** detection (multiple sub-threshold transactions
  aggregating above threshold across time/accounts).
- No **layering** detection (rapid pass-through of funds in→out).
- No cross-account / cross-customer **network analysis** (shared payees,
  circular transfers, mule rings, shell-company fan-out).
- No trade-based money laundering (invoice/pricing mismatch) checks.
- No SWIFT/ISO 20022 message-level monitoring for cross-border wires.
- Rule thresholds ($10k, 5/day, etc.) are Python constants — not
  configurable per jurisdiction/product without a code deploy.

### 2.3 Case management — alert-only, not case-centric
- `Alert` is a flat table; there's no **Case** entity linking multiple
  related alerts on one customer/typology into a single investigation.
- No maker-checker (four-eyes) approval before an SAR/EDD decision closes.
- No SLA/aging tracking, analyst workload balancing, or disposition-code
  taxonomy — just free-text `resolution_notes`.
- No evidence/attachment storage or investigation narrative builder.

### 2.4 Regulatory reporting — not implemented
- No SAR/STR generation or e-filing (FinCEN SAR, goAML XML, jurisdiction
  equivalents).
- No CTR (Currency Transaction Report) automation for large cash
  transactions.
- No FinCEN 314(a)/(b) style information-sharing support.

### 2.5 Model governance (SR 11-7 / regulatory model risk expectations)
- Model registry tracks versions but there's no champion/challenger
  testing, documented validation, bias/fairness testing, or drift
  monitoring dashboard tied to alerting.
- SHAP explanations exist per-score but aren't surfaced in an
  audit-ready model documentation trail.

### 2.6 Security & data protection — needs hardening before production
- ~~`CORSMiddleware` allows `allow_origins=["*"]`~~ — **fixed**: env-driven
  allow-list (`CORS_ALLOWED_ORIGINS`), `*` rejected.
- Secrets (`SECRET_KEY`, DB creds) live in a plaintext `.env` — no
  KMS/Vault/Secrets Manager integration.
- No field-level encryption or masking of PII (DOB, account numbers) at
  rest.
- No MFA for analyst/compliance-officer/admin login.
- `AuditLog` is a normal mutable Postgres table — not tamper-evident
  (no hash-chaining/WORM), which regulators expect for audit integrity.
- Per-IP rate limiting via `slowapi` (stopgap); no WAF in front of the public API yet.

### 2.7 Entity resolution & beneficial ownership
- No UBO (Ultimate Beneficial Owner) tracking for corporate/fund
  customers, no linked-entity graph (shared address/phone/device/IP),
  no corporate structure unwinding.

### 2.8 Real-time / scale
- Pipeline is batch/ETL-oriented; there's no streaming ingestion
  (Kafka/Kinesis) for pre-transaction blocking or sub-second scoring at
  card-authorization time.

### 2.9 Observability
- No Prometheus/Grafana, centralized logging, or alerting on pipeline
  failures, DLQ growth, model drift, or alert-queue aging — only
  mentioned as a "tip" in `QUICK_START.md`, not wired up.

### 2.10 Testing
- No AML-typology-based scenario tests (synthetic structuring/layering
  cases) or backtesting of ML models against historical labeled SARs to
  validate detection rates before shipping a rule/model change.

## 3. Enhancement roadmap

Phased by dependency order. Each phase is independently shippable.

### Phase 4 — Screening & CDD depth (highest regulatory risk today)
| # | Feature | Why | Status |
|---|---|---|---|
| 4.1 | Real sanctions/PEP list ingestion (OFAC, UN, EU, UK HMT) as a scheduled Celery job, versioned & auditable | Booleans today have no defensible source of truth | **Done** — OFAC SDN/Consolidated, UN Consolidated, UK OFSI (free, no-key feeds; EU deferred, needs a paid API key). `app/services/watchlist_ingestion_service.py`, `app/services/watchlist_adapters/`, `watchlist_sources`/`watchlist_entities`/`watchlist_ingestion_runs` tables (migration `0003`) |
| 4.2 | Fuzzy name-matching engine (Jaro-Winkler + phonetic + transliteration) with match-score, replacing exact flags | Real screening needs partial matches, aliases | **Done** — rapidfuzz WRatio + DOB boost, trigram-prefiltered. `app/services/screening_service.py`. Phonetic/transliteration-specific matching not yet added |
| 4.3 | Perpetual KYC — auto re-screen customers when lists update, not just at onboarding | Core FATF ongoing-monitoring requirement | **Done** — screens on customer create/update, plus a nightly post-ingestion re-screen of all customers. `app/tasks/watchlist_tasks.py` |
| 4.4 | Configurable rule thresholds (DB/admin-UI driven, not Python constants) with per-jurisdiction overrides | Compliance needs to tune without redeploys | **Done** — `rule_configs` table (default < GLOBAL < jurisdiction layering), `/api/v1/rule-configs` API, audit-logged edits. `app/services/rule_config_service.py`, migration `0004`. No admin UI yet, API only |
| 4.5 | UBO / beneficial-ownership capture for CORPORATE/FUND customers | Required for corporate CDD | **Done** — `beneficial_owners` table (migration `0005`), ownership-percentage validation (≤100% per customer), verification workflow (PENDING→VERIFIED/REJECTED, COMPLIANCE_OFFICER/ADMIN only), UBOs screened against watchlists same as customers (a confirmed hit also flags the owning entity), CDD-completeness summary. `app/services/beneficial_ownership_service.py`, `/api/v1/customers/{id}/beneficial-owners` |

### Phase 5 — Advanced transaction monitoring
| # | Feature | Why |
|---|---|---|
| 5.1 | Structuring/smurfing detector — rolling aggregation across accounts/customers vs. reporting threshold | Classic evasion pattern the current rules miss |
| 5.2 | Layering detector — rapid in→out fund pass-through scoring | Common laundering typology |
| 5.3 | Network/graph analysis (shared counterparties, circular flows, mule-ring detection) — graph DB or SQL recursive CTEs to start | Single-transaction rules can't see ring structures |
| 5.4 | Trade-based ML (TBML) checks for invoice/pricing anomalies (if trade finance in scope) | FATF Recommendation area |
| 5.5 | Scenario/typology test suite — synthetic structuring & layering cases as regression tests | Prevents silent detection-rate regressions |

### Phase 6 — Case management & regulatory reporting
| # | Feature | Why |
|---|---|---|
| 6.1 | `Case` entity grouping related alerts, with investigation narrative + evidence attachments | Alerts alone don't support real investigations |
| 6.2 | Maker-checker (four-eyes) approval workflow before SAR filing/case closure | Standard control at every bank |
| 6.3 | SAR/STR generation (FinCEN SAR / goAML XML) with e-filing integration | Currently no path from alert to filed report |
| 6.4 | CTR automation for large cash transactions | Regulatory requirement in many jurisdictions |
| 6.5 | Disposition-code taxonomy + SLA/aging dashard for the analyst queue | Operational KPI banks track closely |

### Phase 7 — Model governance & MLOps
| # | Feature | Why |
|---|---|---|
| 7.1 | Champion/challenger framework with side-by-side backtesting | Needed to safely promote new model versions |
| 7.2 | Model drift & performance monitoring with alerting (precision/recall/false-positive rate over time) | Silent model decay is a top regulator finding |
| 7.3 | Documented model validation workflow (independent review sign-off, stored with the model registry entry) | SR 11-7-style expectation |
| 7.4 | Bias/fairness testing across protected attributes | Increasingly expected by regulators |

### Phase 8 — Security & enterprise hardening
| # | Feature | Why |
|---|---|---|
| 8.1 | Lock down CORS to explicit allow-listed origins | `allow_origins=["*"]` is unsafe for a system with financial PII — **Done**: `CORS_ALLOWED_ORIGINS` allow-list (`app/config.py`) |
| 8.2 | Secrets management via Vault/AWS Secrets Manager/KMS, remove plaintext `.env` secrets from disk in prod | Currently `SECRET_KEY`/DB creds sit in plaintext |
| 8.3 | Field-level encryption/masking for PII at rest | DOB, account numbers currently stored in the clear |
| 8.4 | MFA for analyst/compliance/admin roles | Privileged access to financial crime data |
| 8.5 | Tamper-evident audit log (hash-chained rows or WORM storage) | Regulators expect audit integrity, not just an audit table |
| 8.6 | API rate limiting + WAF in front of the public endpoints | Basic production hardening — **Partial**: `slowapi` limiter (`app/rate_limit.py`, 300/min global, 10/min login); WAF still to do |
| 8.7 | Expand RBAC beyond 3 roles (e.g., MLRO, QA/second-line, read-only regulator role) | Real banks segregate duties more finely |

### Phase 9 — Scale & real-time
| # | Feature | Why |
|---|---|---|
| 9.1 | Streaming ingestion (Kafka/Kinesis) alongside the batch ETL pipeline | Needed for pre-transaction blocking use cases |
| 9.2 | Sub-second real-time scoring path for authorization-time blocking | Batch pipeline can't support hold/block decisions |
| 9.3 | Horizontal scaling review for API + scorer under bank-scale transaction volume | Current design is single-node oriented |

### Phase 10 — Observability
| # | Feature | Why |
|---|---|---|
| 10.1 | Prometheus + Grafana for API, pipeline, and Celery metrics | Currently only mentioned as a doc "tip", not implemented |
| 10.2 | Centralized structured logging (ELK/Loki) | No centralized log aggregation today |
| 10.3 | Alerting on pipeline failures, DLQ growth, model drift, alert-queue aging | Ops currently finds out about failures manually |

## 4. Quick wins (low effort, do first)

- ~~Fix `CORSMiddleware(allow_origins=["*"])` in `app/main.py`.~~ **Done** — see `SECURITY.md`.
- ~~Move rule thresholds out of `rules_engine.py` constants into a DB-backed config table.~~ **Done** (Phase 4.4).
- ~~Remove `frontend/phase3/js/patterns.js.backup` from the repo.~~ **Done** (`*.backup`/`*.bak` now gitignored).
- ~~Add a root-level `SECURITY.md` checklist and wire the existing
  `QUICK_START.md` "Security Checklist" items into actual CI gates
  (secret scanning, dependency scanning) rather than a manual checklist.~~
  **Done** — `SECURITY.md` + `.github/workflows/security.yml` (gitleaks, pip-audit).
- ~~Add rate limiting middleware (e.g., `slowapi`) to the FastAPI app as a
  stopgap before a proper WAF is in place.~~ **Done** — `app/rate_limit.py`.

## 5. Suggested sequencing

1. **Phase 4** (screening/CDD) and the **quick wins** — biggest regulatory
   exposure today is defensibility of PEP/sanctions decisions and open CORS.
2. **Phase 8** (security hardening) in parallel — should land before any
   real customer data touches the system.
3. **Phase 5** (advanced monitoring) and **Phase 6** (case management/SAR)
   — the features that turn this from a scoring engine into a full
   investigations platform.
4. **Phase 7** (model governance) — required once ML models are making
   consequential decisions at scale.
5. **Phase 9–10** (scale/observability) — as transaction volume and
   production uptime requirements grow.
