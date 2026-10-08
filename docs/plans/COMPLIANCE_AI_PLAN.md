# KYRO Compliance AI — Implementation Plan

**Branch:** `feature/compliance-ai`
**Status:** Draft for review
**Builds on:** README §3 roadmap (Phases 4–10). This plan is proposed as **Phase 11**.

## 1. Goal

Address five client pain points in KYC/compliance operations by adding an AI layer to KYRO that
**reads, extracts, explains and proposes**, while analysts and compliance officers keep every
decision. Each capability must leave an audit trail a regulator can follow.

| # | Pain point | What KYRO adds | Primary success measure |
|---|---|---|---|
| 1 | Manual document review | Document intake, AI extraction and cross-checks with cited evidence | Analyst minutes per document set |
| 2 | High false-positive investigation | Alert triage copilot, false-positive likelihood model, rule-tuning backtests | False-positive rate **without** losing true positives |
| 3 | Fragmented regulatory information | Versioned regulatory knowledge base with cited Q&A | Time to answer a regulatory question; % answers with citations |
| 4 | No automated data mapping/interpretation | Regulation → obligation → control → rule mapping; data-feed field mapping | Share of obligations mapped to a control; onboarding time for a new data feed |
| 5 | Constantly changing regulations | Change detection, impact assessment, maker-checker rule updates with effective dates | Days from regulatory change to approved rule update |

## 2. Principles (non-negotiable for an AML system)

1. **Human in the loop.** AI never closes an alert, files a SAR/STR, approves a customer or
   activates a rule. It suggests; a named user decides.
2. **Every AI output is evidenced.** Answers and extractions carry citations (document, page,
   section, regulation version) and a confidence. No citation → shown as unverified.
3. **Everything is auditable.** Each AI call is logged (prompt version, model, inputs reference,
   output, citations, user decision) and linked to the case/customer/rule it affected.
4. **Deterministic rules stay the enforcement layer.** AI proposes rule changes; the rules engine
   and `rule_configs` remain what actually generates alerts.
5. **Model risk management.** AI components go through the validation, monitoring and
   champion/challenger process in README Phase 7, in proportion to their influence on
   decisions (see §9.5 on the April 2026 revised model risk guidance, which replaced SR 11-7).
6. **Data protection.** Customer PII is minimized/redacted before leaving KYRO; the provider,
   region and retention terms are an explicit decision (see §9).

## 3. Starting point — what exists today

| Capability | Where | Reuse for |
|---|---|---|
| Analyst disposition labels (`is_false_positive`, `resolution_notes`) | `app/models/alert.py`, `app/routers/alerts.py` | Training data for #2 |
| False-positive rate / precision | `app/services/feedback_service.py` | Baseline + monitoring for #2 |
| ML scoring, SHAP explanations, registry, retraining | `app/ml/` | FP model, explanations (#2) |
| Score-based routing (`LOW_MAX=30`, `MEDIUM_MAX=70`) | `app/services/alert_service.py` | Triage tiers (#2) |
| Rules R001–R010 + DB thresholds per jurisdiction | `app/services/rules_engine.py`, `rule_configs` | Target of mappings and changes (#4, #5) |
| Versioned source ingestion pattern (sources → runs → entities, Celery) | `app/services/watchlist_ingestion_service.py`, `app/tasks/watchlist_tasks.py` | Regulatory source ingestion (#3, #5) |
| Audit log | `app/services/audit_service.py` | AI audit trail (all) |
| ETL ingestion/transformation | `pipeline/` | Field mapping for new data feeds (#4) |
| Kyro Chat UI (answers are currently **scripted**) | `frontend/phase3/js/kyrochat.js` | Front end for regulatory Q&A and case copilot (#2, #3) |
| Case report export (real data) | `frontend/phase3/js/cases.js` | Include AI findings with citations (#1, #2) |

**Code audit (8 Oct 2026):**

| Plan item | Status in code |
|---|---|
| LLM integration / AI settings | Missing: only an OpenAI TTS fallback; `KYRO_LLM_*` exist only as `.env.example` placeholders |
| Kyro Chat answers | Scripted: keyword matching in `app/routers/kyrochat.py` and `kyroScripts.js`, no model |
| Alert outcomes for FP learning | Partial: API stores `is_false_positive` + notes, but **0 alerts resolved** and no reachable Resolve screen |
| FP measurement | Present: `feedback_service.evaluate_performance` (precision, FP rate) |
| ML scoring + explanations + retraining | Present: `app/ml/` (risk scorer, anomaly models, SHAP, registry) |
| Rule thresholds in DB | Present: `rule_configs` per jurisdiction, audit-logged; **no version history or effective dates** |
| Maker-checker approvals | Missing |
| Documents / OCR / extraction | Missing |
| Vector search | Missing in schema; `pgvector` 0.8.1 available in local PostgreSQL 18, not enabled |
| Regulatory sources | Missing; watchlist ingestion provides the pattern |

Gaps: no document storage or text extraction, no LLM integration (only an OpenAI TTS fallback in
`app/routers/tts.py`), no vector search, `rule_configs` edits overwrite in place (no version
history or effective dates), no disposition taxonomy (README 6.5), no maker-checker (README 6.2).

## 4. Phase 11.0 — Shared AI foundation (prerequisite for everything)

| Item | Description | Key files / tables |
|---|---|---|
| 11.0.1 AI gateway | One internal interface (`generate`, `extract_structured`, `embed`) with provider adapters, timeouts, retries, cost/latency metrics, and a global kill switch (`AI_ENABLED`). All AI calls go through it. | `app/ai/gateway.py`, `app/ai/providers/`, `app/config.py` |
| 11.0.2 Prompt registry | Prompts as versioned files with IDs; the version is stored with every output so results are reproducible. | `app/ai/prompts/*.md` |
| 11.0.3 PII redaction | Redact/tokenize names, IDs, account numbers before external calls; re-identify on return. | `app/ai/redaction.py` |
| 11.0.4 AI interaction log | Table recording each call and the human decision on it; linked into `audit_logs`. | `ai_interactions` (migration `0006`) |
| 11.0.5 Retrieval store | Chunked text + embeddings for documents and regulations. Preferred: `pgvector` in the existing PostgreSQL (verify availability on PG 18/Windows and in RDS). | `knowledge_chunks` |
| 11.0.6 Evaluation harness | Golden datasets per feature (extraction accuracy, citation correctness, FP-model recall) run in CI before prompt/model changes ship. Extends README 5.5. | `tests/ai_eval/` |

**Exit criteria:** a test prompt round-trips through the gateway with redaction, is logged in
`ai_interactions`, and the eval harness runs in CI with the AI provider mocked.

### AI configuration

The first provider is an **OpenAI-compatible endpoint** (an LLM gateway in front of Anthropic
Claude Haiku 4.5), so the gateway's first adapter speaks the OpenAI chat-completions protocol
against a configurable base URL. Settings live in `app/config.py` and come from the environment,
never from the repository:

| Setting | Purpose | Example |
|---|---|---|
| `KYRO_AI_ENABLED` | Global kill switch for all AI features | `true` |
| `KYRO_LLM_MOCK` | Return canned responses (tests, CI, demos without a key) | `false` |
| `KYRO_LLM_BASE_URL` | OpenAI-compatible endpoint | `https://<gateway-host>/v1` |
| `KYRO_LLM_API_KEY` | Secret key; local: `local.env`, production: AWS Secrets Manager (README 8.2) | *(never committed)* |
| `KYRO_LLM_MODEL` | Model name as the gateway expects it | `claude-haiku-4-5-20251001` |
| `KYRO_LLM_TIMEOUT_SECONDS` | Per-call timeout | `30` |

Notes:
- The settings are generic so the provider can change (direct Anthropic API, a cloud-hosted
  model, or another gateway) without code changes; only the adapter differs if the protocol does.
- A gateway in front of the model is an additional processor of customer data: compliance must
  approve its data-handling, retention and region before real KYC data is sent (§9). Until then,
  run with `KYRO_LLM_MOCK=true` or with synthetic data only.
- Haiku 4.5 suits high-volume extraction and triage; harder reasoning tasks (impact assessment in
  11.5) may need a larger model. The model is selectable per task via the prompt registry.

## 5. Workstreams per pain point

### 11.1 Document review copilot — pain point 1

1. **Document intake:** `documents` table + storage (local disk in dev, S3 in prod), linked to
   customer and/or case; type (ID, proof of address, company registry extract, financial
   statement, source-of-funds letter), hash, uploader, retention date. Upload UI in Case Details
   and customer profile.
2. **Text extraction:** native PDF/DOCX text first; OCR only for scans (choose engine — §9).
3. **Structured extraction:** per document type, extract fields (name, DOB, address, registration
   number, directors/UBOs, dates, amounts) with page-level citations and confidence.
4. **Cross-checks (deterministic):** compare extracted fields with the customer record, UBO
   register (`beneficial_owners`) and screening results; flag mismatches (name, DOB, address,
   expired documents, UBO missing from register).
5. **Analyst review UI:** side-by-side document viewer and fields; accept / edit / reject per
   field; accepted values can update the customer record via the normal audited API.
6. **Case integration:** document findings appear in Case Details and the exported case report,
   with citations.

**Acceptance:** for a labelled set of KYC packs, field extraction precision ≥ agreed target,
every extracted value has a page citation, and no customer record changes without an explicit
analyst accept.

### 11.2 False-positive reduction — pain point 2

0. **Make outcomes recordable (prerequisite):** the 8 Oct 2026 audit found **0 resolved alerts**;
   the resolve API exists but no reachable screen calls it. Add a Resolve action to Review Cases
   (outcome + reason codes from §9.6 + required notes), so labels start accumulating immediately.
1. **Baseline first:** report current FP rate, alert volumes and time-to-disposition per rule and
   rule combination (from `feedback_service` + alert timestamps). Needed to prove impact.
2. **Better labels:** the outcome + reason taxonomy in §9.6 (README 6.5), required on every
   resolution.
3. **Triage copilot:** for each alert, gather context (customer profile, prior alerts and
   dispositions, related transactions, screening, documents) and produce a short, cited
   investigation summary with a *suggested* disposition. Shown in Case Details; analyst decides.
4. **FP-likelihood model:** classifier trained on dispositions (features: rule combination,
   customer history, counterparty history, amounts vs baseline, prior FPs for the same pattern),
   with SHAP explanations. Used to **order** the queue, not to auto-close.
5. **Rule-tuning recommendations:** identify rules/thresholds with high FP share; propose
   `rule_configs` changes and **backtest** them on historical alerts, showing true positives that
   would have been missed before anyone can approve.
6. **Monitoring:** FP rate, recall on confirmed true positives, and model drift on the
   dashboard (ties to README 7.2).

**Acceptance:** on a held-out period, ordering by FP-likelihood puts ≥ X% of confirmed true
positives in the top tier, and approved rule changes show **no loss of confirmed true positives**
in backtest. (X agreed with compliance before training.)

### 11.3 Regulatory knowledge base — pain point 3

1. **Sources:** start with SEC regulations via the eCFR API, Federal Register notices, FINRA
   rules and regulatory notices, and internal policies uploaded as documents. Confirm the
   licensing/terms of use for each external source before ingesting (§9).
2. **Ingestion:** same pattern as watchlists — `regulatory_sources` → `regulatory_ingestion_runs`
   → `regulatory_documents` (versioned) → `regulatory_sections` (rule/section granularity),
   scheduled by Celery.
3. **Search and Q&A:** semantic + keyword search over sections; Kyro Chat answers regulatory
   questions **only from retrieved sections**, with section-level citations and the version date.
   Replaces the scripted answers for regulatory questions.
4. **Obligations register:** extract obligations (who must do what, by when, under which
   section) into `obligations`, each linked to its source section and version.

**Acceptance:** answers on a curated question set cite the correct section in ≥ agreed % of
cases; questions outside the corpus get "not found in sources", not a guess.

### 11.4 Data mapping & interpretation — pain point 4

1. **Obligation → control → rule mapping:** AI proposes how each obligation maps to KYRO
   controls (rules R001–R010, `rule_configs`, review cycles, screening, document requirements),
   e.g. a cash reporting threshold obligation → R001 amount threshold for that jurisdiction.
2. **Mapping review UI:** compliance confirms/edits mappings; unmapped obligations are shown as
   coverage gaps.
3. **Traceability matrix:** regulation version → obligation → control → rule config → alerts it
   produced. Exportable for audits.
4. **Data-feed field mapping:** when onboarding a new client file/feed, AI suggests mappings from
   source columns to KYRO's schema (customers, accounts, transactions) with sample-value checks;
   the confirmed mapping is saved as pipeline config in `pipeline/`.

**Acceptance:** every active rule config is traceable to at least one obligation or marked
"internal policy"; a new sample feed can be mapped and loaded without code changes.

### 11.5 Regulatory change management — pain point 5

1. **Change detection:** each ingestion run diffs new section versions against the previous
   ones; Federal Register/FINRA notices are classified as relevant or not.
2. **Impact assessment:** for each relevant change, AI drafts a summary and lists affected
   obligations, mapped controls and rule configs (via the 11.4 traceability matrix).
3. **Versioned, effective-dated rules:** extend `rule_configs` with version history,
   `effective_from`/`effective_to` and a link to the triggering change (migration).
4. **Maker-checker:** proposed rule changes go through draft → backtest → approval by a second
   user → scheduled activation (README 6.2). Rejected changes keep their reasoning.
5. **Change log:** a dashboard of open regulatory changes, owners, status and deadlines.

**Acceptance:** a simulated regulatory change flows from detection to an approved,
effective-dated rule update, fully traceable, without touching code.

## 6. Data model additions (indicative)

| Table | Purpose | Workstream |
|---|---|---|
| `ai_interactions` | Every AI call, prompt version, model, output, citations, user decision | 11.0 |
| `knowledge_chunks` | Text chunks + embeddings for retrieval | 11.0 |
| `documents`, `document_extractions` | Uploaded files and extracted fields with citations/status | 11.1 |
| `alert_dispositions` (or columns on `alerts`) | Disposition taxonomy | 11.2 |
| `regulatory_sources`, `regulatory_ingestion_runs`, `regulatory_documents`, `regulatory_sections` | Versioned regulatory corpus | 11.3 |
| `obligations`, `obligation_mappings` | Obligations and their mapped controls | 11.3–11.4 |
| `rule_config_versions`, `regulatory_changes`, `change_approvals` | Effective-dated rule history and maker-checker | 11.5 |
| `feed_mappings` | Saved source-to-schema mappings for data feeds | 11.4 |

## 7. Sequencing

Each step is shippable on its own. Durations are rough for a small team (2–3 engineers) and
should be re-estimated after 11.0.

| Order | Deliverable | Depends on | Rough size |
|---|---|---|---|
| 1 | 11.0 AI foundation + provider decision | — | 2–3 weeks |
| 2 | 11.2 steps 0–2: Resolve flow with outcome/reason codes, then FP baseline | — (can run in parallel with 1; start immediately so labels accumulate) | 1–2 weeks |
| 3 | 11.1 Document review copilot | 11.0 | 4–6 weeks |
| 4 | 11.2 steps 3–6: triage copilot, FP model, rule backtests | 11.0, labels from step 2 | 4–6 weeks |
| 5 | 11.3 Regulatory knowledge base | 11.0 | 4–5 weeks |
| 6 | 11.4 Mapping + traceability | 11.3 | 3–4 weeks |
| 7 | 11.5 Change management + maker-checker | 11.3, 11.4 | 4–5 weeks |

Recommended first client-visible milestone: **Resolve flow + FP baseline, then the triage
copilot** (steps 2 and 4). The Resolve flow should ship first because the FP model needs 4–8 weeks
of recorded outcomes before it can be trained.

### Implementation status (8 Oct 2026)

| Item | Status |
|---|---|
| 11.0.1–11.0.4 AI gateway, prompt registry, PII redaction, `ai_interactions` log | Done (`app/ai/`, `app/routers/ai.py`, migration `0006`); mock mode, no real provider configured |
| 11.0.5 Retrieval store | Done as full-text search (`knowledge_chunks`, `app/ai/retrieval.py`, `GET /ai/search`, migration `0008`); vector/hybrid search waits for the embeddings decision (§9.2). Store is empty until 11.3 ingestion |
| 11.0.6 Evaluation harness | Done (`tests/ai_eval/`: redaction and retrieval golden sets, run in CI); extraction, Q&A and FP-model sets are added with those features |
| 11.2 step 0 Resolve flow with outcome + reason codes (§9.6) | Done (`/alerts/{id}/resolve`, `/alerts/resolution-options`, Resolve in Case Details, migration `0007`); second reviewer for `FALSE_POSITIVE` + `OTHER` waits for maker-checker (11.5) |
| 11.2 steps 1–2 FP baseline per rule | API done (`GET /alerts/disposition-baseline`: FP rate, volumes, time-to-disposition, reasons per rule and rule combination); no dashboard view yet, and numbers are empty until alerts are resolved |

| 11.2 UI | Review Cases shows the false-positive baseline per rule and a per-row Resolve action |
| 11.3 steps 1–3 Regulatory knowledge base | Done for eCFR: `regulatory_sources` / `regulatory_ingestion_runs` / `regulatory_sections` (migration `0009`), daily Celery refresh, `/regulatory/*` endpoints, cited Q&A (`/regulatory/ask`) used by Kyro Chat. Loaded: 31 CFR Parts 1010 and 1023, 17 CFR 240.17a-8. Versions are kept per section (no separate `regulatory_documents` table). Not yet: Federal Register, FINRA references, internal policies, obligations register (step 4) |
| Known limits | Search is keyword-only, so the best passage is not always ranked first (hybrid search, §9.2). AI answers need a real provider; until then Kyro Chat shows the source passages |

## 8. Testing & governance

- Unit/API tests per workstream in `tests/api`; AI components tested with the provider mocked.
- `tests/ai_eval/` golden sets: extraction accuracy, citation correctness, Q&A groundedness,
  FP-model recall/precision; thresholds enforced in CI.
- Model documentation and sign-off stored with the model registry (README 7.3); drift and
  performance monitoring on the dashboard (README 7.2).
- Security review before go-live: PII redaction, access control on documents (RBAC, README 8.7),
  encryption at rest for uploaded documents (README 8.3).

## 9. Decisions — research and recommendations (8 Oct 2026)

Each recommendation below is a proposal for the product owner and compliance to confirm. Sources
are listed in §11.

### 9.1 LLM provider and hosting

**Recommendation:** use the proposed OpenAI-compatible gateway serving Claude Haiku 4.5 for
development **with synthetic data or `KYRO_LLM_MOCK=true` only**. Before any real customer data is
sent, compliance approves the gateway's data-handling, retention, region and DPA terms, or KYRO
switches to a direct provider account. The gateway design (§4) makes that a configuration change.

### 9.2 Vector store

**Recommendation:** `pgvector` in the existing PostgreSQL, with **hybrid retrieval**.

- Already available: `pgvector` 0.8.1 is installed in the local PostgreSQL 18 (not yet enabled),
  and Amazon RDS for PostgreSQL supports pgvector 0.8.x, so dev and production match with no new
  service to run.
- pgvector 0.8 adds iterative index scans, which keep filtered searches (e.g. "only sections of
  31 CFR 1023, current version") from returning too few results.
- **Hybrid search:** combine vector similarity with PostgreSQL full-text search and merge the two
  rankings with Reciprocal Rank Fusion (RRF, k = 60). Regulatory questions are full of exact
  references ("Rule 3310", "§ 1023.320") that pure vector search misses; published field notes
  report a large precision gain from adding full-text search.
- **Embeddings:** Anthropic models do not produce embeddings. Options: an embeddings endpoint on
  the chosen gateway (confirm availability), or a separate embeddings provider. Full-text search
  works from day one, so 11.3 can ship keyword search first and add vectors when embeddings are
  decided.

### 9.3 OCR engine

**Recommendation:** a tiered pipeline, cheapest and most private first.

1. **No OCR when possible:** extract native text from digital PDFs/DOCX (most bank statements and
   registry extracts are digital).
2. **Scans in production:** Amazon Textract (`AnalyzeDocument` with forms/tables) in the same AWS
   region as KYRO, so documents stay within KYRO's cloud account. Pay-per-page, no licence.
3. **Identity documents:** Textract `AnalyzeID` only covers **US** passports and driver's
   licences. KYRO customers are international, so non-US IDs go through tier 2 plus field
   extraction by the LLM from the OCR **text** (redactable), not by sending ID images to the
   gateway.
4. **No-cloud deployments:** PaddleOCR in a container as the open-source fallback. Benchmarks put
   it clearly ahead of Tesseract on tables and photographed documents; Tesseract is fine for
   clean printed text only.

### 9.4 Regulatory sources and jurisdictions (first release)

**Recommendation:** start with **US broker-dealer AML**, the scope the client named (FINRA, SEC).

| Source | Content | Access | Terms |
|---|---|---|---|
| eCFR (Versioner API) | 31 CFR Part 1010 (incl. 1010.230 beneficial ownership / CDD rule) and Part 1023 (broker-dealers: CIP 1023.220, SAR 1023.320); 17 CFR 240.17a-8 | Free, keyless JSON/XML API with point-in-time text and version history | US Government work, public domain |
| Federal Register API | Final/proposed rules and notices from FinCEN and SEC (change detection for 11.5) | Free, keyless REST API (JSON/CSV) | Public domain |
| FinCEN / SEC guidance | CDD Rule FAQs, FinCEN alerts, SEC AML Source Tool for broker-dealers, SEC AML risk alerts | Public web pages/PDFs | Public domain (verify per page) |
| FINRA | Rule 3310 (AML programme), Rule 2090 (KYC), regulatory notices | **Rulebook API (paid)** via the FINRA API Platform; covers the 40 most-viewed rules with taxonomy tags | Website terms: **non-commercial personal/professional use only**; API terms: no redistribution or sublicensing |
| Internal policies | Client's AML/KYC policies and procedures | Uploaded as documents (11.1 intake) | Client-owned |

**FINRA terms of use:** scraping finra.org into KYRO is **not** permitted for a commercial product
without FINRA's written consent. Options: (a) each client firm subscribes to the FINRA Rulebook
API under its own licence and KYRO ingests it into **that client's** tenant only; or (b) KYRO
obtains a commercial licence from FINRA. Until one is in place, KYRO stores only FINRA rule
**references** (rule numbers, titles, links) and maps obligations to them, without storing rule
text. Legal should confirm the chosen option.

Later jurisdictions (after US): UK (FCA Handbook, MLRs 2017), EU (AMLR/AMLA), each with its own
licensing review.

### 9.5 False-positive targets

**Prerequisite (from the 8 Oct 2026 code audit):** KYRO has **0 resolved alerts**. The resolve API
records `is_false_positive`, but no reachable screen calls it (the alerts page is not routed, and
Review Cases has no Resolve action). Step 11.2.0 below fixes this; targets can only be set after
4–8 weeks of recorded outcomes.

**Recommendation:** measure first, then commit to relative targets with a hard recall floor.

| Metric | Target | Notes |
|---|---|---|
| Recall on confirmed true positives (incl. SAR-filed cases) | **No loss** versus the current rules in backtest (hard floor) | Any rule or model change failing this is rejected |
| False-positive rate | **-30% in phase 1**, -50% stretch, versus the measured baseline | Industry baseline for rule-based monitoring is commonly cited at 90–95%; vendors report 40–60% reductions with ML, so start conservatively |
| Alert-to-SAR conversion | Track; trend upward | Commonly cited healthy range 5–15%, versus under 5% typical |
| Median time to disposition | -40% with the triage copilot | Measured per analyst and per rule |
| Below-the-line testing | Sample alerts just under each threshold quarterly | Confirms tuning is not hiding true positives |

**Model governance:** the April 2026 revised interagency model risk management guidance (Fed
SR 26-2 / OCC Bulletin 2026-13) replaced SR 11-7 and rescinded the 2021 BSA/AML model risk
statement. It takes a risk-based, proportional approach and is aimed mainly at banks over $30B in
assets. KYRO should still document, validate and monitor the FP model and AI components in
proportion to their influence on decisions (README Phase 7), so client banks can fit them into
their own model inventory.

### 9.6 Resolution reasons (disposition taxonomy)

**Recommendation:** two required fields on every resolution, plus mandatory notes. Examiners
expect the reason for **not** filing a SAR to be documented, so free text alone is not enough.

**Outcome** (one):

| Code | Meaning |
|---|---|
| `SAR_FILED` | Suspicion confirmed; SAR/STR filed (link the filing reference) |
| `ESCALATED` | Passed to senior compliance / MLRO for decision |
| `TRUE_POSITIVE_NO_SAR` | Activity matched the rule and needed review, but no suspicion after investigation |
| `FALSE_POSITIVE` | Alert did not represent the risk the rule targets |

**Reason** (one or more):

| Code | Typical outcome | Feeds |
|---|---|---|
| `EXPECTED_ACTIVITY_DOCUMENTED` | True positive, no SAR | Customer profile update |
| `CUSTOMER_EXPLANATION_VERIFIED` | True positive, no SAR | Evidence attached |
| `KNOWN_COUNTERPARTY` | False positive | Counterparty allow-list proposal |
| `RULE_TOO_BROAD` | False positive | Rule-tuning backlog (11.2 step 5) |
| `THRESHOLD_TOO_LOW` | False positive | Rule-tuning backlog |
| `DATA_QUALITY_ISSUE` | False positive | Data-quality ticket to pipeline owners |
| `DUPLICATE_ALERT` | False positive | Alert de-duplication |
| `SCREENING_NAME_MISMATCH` | False positive | Screening threshold review |
| `STRUCTURING_SUSPECTED`, `LAYERING_SUSPECTED`, `SANCTIONS_EXPOSURE`, `UNEXPLAINED_SOURCE_OF_FUNDS`, `OTHER` | SAR filed / escalated | SAR narrative inputs |

Notes are required for every outcome; `FALSE_POSITIVE` with reason `OTHER` requires a second
reviewer. The codes become labels for the FP model and drive the rule-tuning backlog.

## 10. Out of scope

- Autonomous alert closure, SAR/STR filing or customer approval/rejection by AI.
- Activating rule changes without maker-checker approval.
- Legal interpretation presented as advice; KYRO surfaces cited source text and drafts, and
  compliance owns the interpretation.

## 11. Sources

- FINRA Website Terms of Use — https://www.finra.org/terms-of-use
- FINRA API Terms of Service — https://developer.finra.org/finra-api-terms-service
- FINRA Special Notice: machine-readable rulebook (Oct 2022) — https://www.finra.org/rules-guidance/notices/special-notice-102122
- FINRA Rulebook Search Tool (FIRST) — https://www.finra.org/rules-guidance/rulebooks/finra-rulebook-search-tool-first
- eCFR developer resources — https://www.ecfr.gov/reader-aids/ecfr-developer-resources/understanding-ecfr-dates
- Federal Register API — https://www.federalregister.gov/reader-aids/developer-resources/rest-api
- 31 CFR 1010.230 beneficial ownership — https://www.law.cornell.edu/cfr/text/31/1010.230
- SEC AML Source Tool for broker-dealers — https://www.sec.gov/about/divisions-offices/division-trading-markets/broker-dealers/anti-money-laundering-aml-source-tool-broker-dealers
- FinCEN CDD Rule FAQs — https://www.fincen.gov/resources/statutes-and-regulations/cdd-rule-faqs
- Amazon RDS for PostgreSQL pgvector 0.8 — https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql
- Hybrid search with pgvector + full-text + RRF — https://dev.to/lpossamai/building-hybrid-search-for-rag-combining-pgvector-and-full-text-search-with-reciprocal-rank-fusion-6nk
- Amazon Textract AnalyzeID (US IDs only) — https://docs.aws.amazon.com/textract/latest/dg/how-it-works-identity.html
- Amazon Textract pricing — https://aws.amazon.com/textract/pricing/
- PaddleOCR vs Tesseract benchmark — https://docsapi.co/resources/blogs/paddleocr-vs-tesseract-vs-docsapi
- False-positive benchmarks — https://www.facctum.com/blog/aml-false-positive-report, https://www.unit21.ai/blog/reduce-false-positives-in-aml-transaction-monitoring
- Fed SR 26-2 revised model risk guidance (Apr 2026) — https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm
- OCC Bulletin 2026-13 — https://www.occ.gov/news-issuances/bulletins/2026/bulletin-2026-13.html
- FFIEC BSA/AML Manual, Suspicious Activity Reporting — https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04
