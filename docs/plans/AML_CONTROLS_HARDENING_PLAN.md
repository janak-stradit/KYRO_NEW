# KYRO AML Controls Hardening — Implementation Plan

**Branch:** `feature/aml-controls-hardening` (from `feature/compliance-ai`)
**Status:** Draft for review. Regulatory deadlines in §5 must be confirmed by Compliance before the workflows are finalised.
**Builds on:** `docs/plans/COMPLIANCE_AI_PLAN.md` (Phase 11). This plan is proposed as **Phase 12**.

## 1. Goal

Tighten six controls raised in the compliance review, so that KYRO's access model, SAR handling,
deadlines, screening and AI use stand up to an examiner:

| # | Workstream | Outcome |
|---|---|---|
| 1 | Administrator and SAR permissions | Admins run the system but have no routine access to SAR content or decisions; emergency access is time-bound and audited |
| 2 | SAR confidentiality | SAR narratives, filing details and filing status are visible only to authorised roles; Team Leads see a neutral compliance status |
| 3 | Regulatory deadline tracking | Risk-based case SLAs, a shorter clock for potential-SAR cases, and separate filing deadlines |
| 4 | Sanctions screening | Fuzzy + phonetic matching, aliases, transliteration and identifier checks, all configurable |
| 5 | AI governance and attestation | AI summaries and narratives cannot be used until an investigator attests them against source records; wider data masking |
| 6 | Role permission matrix and E2E testing | Documented permissions for all ten roles, validated by scenario tests |

Later sprints (not in scope here): investigation stages, KYC transaction-history visibility, rule
governance, data reconciliation.

## 2. Current state (code audit, 11 Oct 2026)

| # | What exists | Gap |
|---|---|---|
| 1 | Permission-based RBAC in `app/permissions.py`: 10 roles + 2 legacy. Endpoints check permissions, not role names. | **`ADMIN` holds every permission** (`set(PERMISSIONS)`), including `sar.view` and `sar.approve`. Legacy `COMPLIANCE_OFFICER` holds everything except three admin permissions. No emergency ("break-glass") access concept. |
| 2 | `app/visibility.py` hides a case, its documents and the fact a SAR was filed from roles without `sar.view` (returned as 404). | Protection starts only once `resolution_outcome = SAR_FILED`. A case **escalated with a SAR recommendation** is fully visible (notes, draft narrative, reasons) to Team Lead, L2 and others. `sar_reference` and `resolution_notes` are not separated from general case data. No "general compliance status" for Team Leads. Draft narratives are returned to the caller but not stored or access-controlled. |
| 3 | One target per risk band: `CASE_TARGET_DAYS_HIGH/MEDIUM/LOW` = 5/10/20 days (`app/config.py`), measured from `created_at`; overdue filter in `app/routers/alerts.py` (`_overdue_condition`). | No separate clock for potential-SAR cases, no "date of initial detection", no filing deadline (e.g. SAR, continuing-activity SAR, CTR), no warnings before a breach, no deadline history. |
| 4 | `app/services/screening_service.py`: pg_trgm candidate search, rapidfuzz whole-name scoring, word-order tolerant, AKA names checked, DOB adds +8. Thresholds 92 (confirmed) / 75 (potential) in settings. | No phonetic matching (Double Metaphone etc.), transliteration is only an ASCII strip (`NFKD`), no identifier matching (passport, national ID, registration no., vessel IMO) even though `raw_data` holds them, no per-list or per-entity-type thresholds, and a confirmed match is decided on score alone. |
| 5 | AI gateway (`app/ai/gateway.py`) logs every call to `ai_interactions` with a `human_decision` field (ACCEPTED/EDITED/REJECTED). `Redactor` masks known names and counterparties plus email, IBAN, dates, phone and 8–19-digit numbers. | Case **summary is saved straight onto the alert** (`alerts.summary`) without attestation; `human_decision` is only set for obligations. Draft narrative has no review step. Redaction misses addresses, transaction references, short account numbers, customer IDs, passport/ID numbers, postcodes. |
| 6 | `tests/api/test_permissions.py` and `test_visibility.py` (~30 tests) cover key separations: L1 vs L2, MLRO-only SAR approval, maker-checker on rules and QA. | No written matrix covering every permission for every role, no generated check that the code matches the matrix, no end-to-end scenarios across a full case life cycle. |

## 3. Design principles

1. **Least privilege by default.** No role gets SAR access as a side effect of being powerful.
2. **Deny is invisible.** Hidden records stay 404, as `visibility.py` does today.
3. **Every exception is logged.** Emergency access, attestations and SAR views write to the audit log with reason and expiry.
4. **Configuration, not code.** SLA days, filing deadlines and screening thresholds live in versioned settings or DB tables, changed through maker-checker.
5. **AI proposes, a named person attests.** Nothing AI-written reaches a case record, report or export without attestation.

## 4. Workstream 1 — Administrator and SAR permissions

**Changes**
- `app/permissions.py`
  - `ADMIN` becomes "system administrator": users, configuration, feeds, ML, AI admin, audit read. Remove `sar.view`, `sar.approve`, `alerts.close*`, `alerts.escalate`, `alerts.qa`, `rules.approve`, `rules.edit_direct` from `ADMIN`.
  - Add a new `sar.content` permission (read narrative, filing details, `sar_reference`) separate from `sar.view` (know a case is SAR-sensitive). Initially: MLRO only (+ AUDITOR read-only, to confirm).
  - Legacy `COMPLIANCE_OFFICER`: remove SAR permissions or migrate its users to MLRO / Team Lead, with a decision recorded by Compliance.
- **Emergency access (break-glass)**
  - New table `emergency_access_grants` (`user_id`, `scope` = `SAR_READ`, `alert_id` optional, `reason`, `approved_by`, `starts_at`, `expires_at` ≤ 4h, `revoked_at`).
  - Request → approval by MLRO (or a second admin if the MLRO is unavailable — to confirm) → grant checked in `has_permission` / `visibility.py` alongside role permissions.
  - Every read under a grant writes an `EMERGENCY_ACCESS` audit row; grants expire automatically; MLRO gets a notice of each use.
- `app/models/audit.py`: add `SAR`, `EMERGENCY_ACCESS` entity types and `VIEW` action (migration `0021`).

**Tests:** admin gets 404 on SAR cases; admin cannot approve a SAR; grant allows access only within window and scope; expired/revoked grant denies; every access audited.

## 5. Workstream 3 — Regulatory deadline tracking

Placed before workstream 2 in the build order because SAR confidentiality depends on the
"potential SAR" stage it introduces.

**Changes**
- Alert fields (migration `0022`): `detected_at` (date of initial detection, defaults to `created_at`, editable with reason), `sla_due_at`, `sar_candidate_at`, `filing_due_at`, `filing_type`, `filed_at`.
- New `deadline_policies` table, maker-checker edited by MLRO:
  - Case SLA by risk band (today's 5/10/20 days move here).
  - Shorter SLA once a case is marked **potential SAR** (proposal: 5 days to MLRO decision).
  - Filing deadlines by jurisdiction and type. **Values to be confirmed by Compliance**, e.g. US FinCEN: SAR within 30 calendar days of initial detection (up to 60 if no suspect is identified); continuing-activity SAR within 120 days of the previous filing; CTR within 15 days. UK: SAR "as soon as practicable"; DAML 7-working-day notice period.
- `app/services/deadline_service.py`: computes due dates, statuses `ON_TRACK / DUE_SOON / BREACHED`, recalculates on stage change.
- Celery beat task: daily scan, notices to assignee, Team Lead and MLRO at 75% and on breach.
- UI: SLA chip on work queue and case page; separate "Filing deadline" panel visible only with `sar.view`; dashboard tile "deadlines due this week".
- Existing `overdue` filter switches to `sla_due_at`.

**Tests:** due-date maths per policy; potential-SAR shortens the clock; filing deadline hidden from roles without `sar.view`; breach notices fire once.

## 6. Workstream 2 — SAR confidentiality

**Changes**
- New alert flag `sar_sensitive` set when a case is escalated with a SAR recommendation or marked potential SAR (from workstream 3), not only when filed.
- `visibility.py`: sensitivity rule uses `sar_sensitive` instead of `resolution_outcome == SAR_FILED`.
- **Field-level masking** in alert/case responses: for users without `sar.content`, drop `resolution_notes`, `resolution_reasons`, `sar_reference`, narrative, filing fields, and SAR-related notes and timeline events.
- **General compliance status** for Team Leads: a neutral status (`WITH_MLRO`, `CLOSED`) and age; no outcome, no reason, no SAR wording. Team Lead keeps queue counts and workload.
- Store draft narratives in a new `sar_narratives` table (versioned, `sar.content` only) instead of returning them unsaved.
- Exports (`frontend/phase3/js/cases.js` report), Kyro Chat and dashboard queries use the same masking helper.
- Customer risk factor "SAR filed in last 12 months" shown as "Internal compliance factor" to roles without `sar.view`.

**Tests:** Team Lead sees `WITH_MLRO` but no narrative/reference; L2 loses access after escalation unless assigned by MLRO; chat and export do not leak SAR fields; tipping-off check — customer-facing requests never reference SAR state.

## 7. Workstream 4 — Sanctions screening enhancements

**Changes** (`app/services/screening_service.py`, `watchlist_adapters/`)
- **Phonetic:** Double Metaphone codes per name part, stored on `watchlist_entities` (`phonetic_keys` JSONB, GIN index); candidate search unions trigram and phonetic hits.
- **Transliteration:** normalise Cyrillic/Arabic/Greek etc. with a transliteration library (e.g. `anyascii`) plus a curated variant table (Mohammed/Muhammad/Mohamed); applied to both sides.
- **Aliases:** keep AKA checks; add weak/strong alias quality from source data and score weak AKAs lower.
- **Identifiers:** extract passport, national ID, tax ID, company registration, IMO/vessel from `raw_data` into a `watchlist_identifiers` table; customers/UBOs get matching identifier fields. Exact identifier match → strong evidence; identifier **mismatch** lowers the score and is shown to the analyst.
- **Configurable:** `screening_policies` table — thresholds per list and entity type, phonetic on/off, DOB tolerance (year only, ±1 year); maker-checker.
- Match details record which methods fired (fuzzy, phonetic, alias, identifier, DOB) so the decision is explainable.
- Re-screen all customers after rollout; compare hit volume against today's baseline before switching on in production.

**Tests:** labelled test set of true matches and near misses (transliterated, reordered, phonetic, alias, identifier conflict); measure recall and alert volume before/after.

## 8. Workstream 5 — AI governance and human attestation

**Changes**
- Summary and narrative become **drafts**: `ai_drafts` (or reuse `ai_interactions`) with status `DRAFT → ATTESTED / REJECTED`.
- Attestation step: investigator sees draft side by side with the source facts (transactions, screening, documents), ticks a confirmation ("I have checked this against the source records"), may edit; stored with user, time, and diff. Sets `ai_interactions.human_decision`.
- `alerts.summary` is written only after attestation; reports, exports and SAR narratives accept only attested text. Attester cannot be the only approver of a SAR built from it (MLRO still approves).
- **Masking** (`app/ai/redaction.py`, `_sensitive_names` in `case_file.py`): add customer IDs, account numbers from the DB (exact values, any length), addresses, postcodes, transaction references, passport/ID numbers, company registration numbers; add a test that sends a full case through and asserts none of the known identifiers leave KYRO.
- AI dashboard: attestation rate, edit rate, rejection rate per prompt version (model-risk monitoring input).

**Tests:** unattested summary not shown in report/export; attestation audited; redaction test over seeded case data.

## 9. Workstream 6 — Role permission matrix and end-to-end testing

**Deliverables**
- `docs/ROLE_PERMISSION_MATRIX.md`: generated from `ROLE_DEFINITIONS` (script `scripts/role_matrix.py`) — every permission × every role, plus visibility rules and the limits text; reviewed and signed off by Compliance.
- Snapshot test: matrix in the doc equals the code; any permission change fails the test until the doc is regenerated and reviewed.
- Endpoint inventory test: every mutating route has a `require_permission` (no route relies on login alone).
- Scenario tests (`tests/e2e/`): full life cycles run as each role —
  1. Alert → L1 false positive → QA pass
  2. Alert → L1 escalate → L2 investigate → potential SAR → MLRO files SAR (Team Lead sees only `WITH_MLRO`; admin sees nothing)
  3. Sanctions hit via alias/transliteration → confirm → customer flagged
  4. Rules owner proposes threshold → MLRO approves → effective date
  5. Admin requests emergency access → approved → expires
  6. AI summary drafted → attested → appears in export
- Gap log of anything the scenarios expose, fed into the sprint backlog.

## 10. Delivery plan

| Sprint | Scope | Depends on |
|---|---|---|
| S1 ✅ | WS6 matrix generator + drift test · endpoint inventory test · WS1 admin permission split · SAR-read audit (`SAR`/`VIEW`) · login on Kyro Chat/TTS | — |
| S2 | WS1 emergency access + maker-checker on granting SAR-bearing roles · WS3 deadline model, policies, SLA clocks | S1 |
| S3 | WS2 `sar.content`, `sar_sensitive`, field masking, Team Lead status, stored narratives · WS3 notices + UI | S2 |
| S4 | WS5 attestation + extended masking · WS4 phonetic, transliteration, policies | S1 |
| S5 | WS4 identifiers + re-screen and baseline · WS6 E2E scenarios, gap log · UAT with Compliance | S3, S4 |

Migrations: `0021` audit types (done in S1; the emergency access table moves to S2's migration), `0022` deadlines, `0023` SAR sensitivity + narratives,
`0024` AI drafts/attestation, `0025` screening identifiers, phonetic keys, policies.

## 11. Decisions needed before build

1. Who approves emergency access, and maximum duration.
2. Whether AUDITOR gets `sar.content` (read-only) or only `sar.view`.
3. What happens to existing `COMPLIANCE_OFFICER` and `ADMIN` users who currently use SAR functions.
4. Jurisdictions and confirmed filing deadlines for §5.
5. Potential-SAR SLA (proposed 5 days) and warning thresholds.
6. Screening thresholds per list and acceptable change in hit volume.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Removing admin SAR access locks out current users mid-case | Migrate roles before release; emergency access available from day one |
| Phonetic/transliteration matching floods analysts with hits | Policy thresholds, baseline comparison, staged rollout per list |
| Masking breaks existing screens and exports | Single masking helper with tests on every SAR-bearing response |
| Deadline values wrong for a jurisdiction | Policies are data, confirmed by Compliance, maker-checker edited |

## 13. Sprint 1 log (11 Oct 2026)

**Done**
- `ADMIN` no longer holds any permission in `DECISION_PERMISSIONS` (`app/permissions.py`): no SAR view or approval,
  no case resolution, escalation, assignment or QA, no rule, customer, document or KYC changes. It keeps users,
  data loads, model training, AI admin, audit read and read-only view of non-SAR cases.
- Opening a SAR-filed case writes a `SAR` / `VIEW` audit entry (`app/visibility.py: record_sar_view`, migration `0021`).
- `docs/ROLE_PERMISSION_MATRIX.md`, generated by `scripts/role_matrix.py`; `tests/api/test_role_matrix.py` fails if it drifts.
- Endpoint inventory test: every write endpoint needs a permission check or an explicit, reviewed exemption.
- Found by the inventory: Kyro Chat (`/chat/*`, `/agent/*`, `/streaming/*`) and `/tts/speak` needed **no login**, and
  chat alert lists ignored case visibility. All now require a signed-in user and filter by `alert_conditions`.

**Changed from the plan**
- `sar.content` moves to S3: until field masking exists every role with `sar.view` would also hold it, so it would change nothing.

**Open, for S2**
- An administrator can still create a user with a SAR-bearing role (e.g. MLRO) and sign in as them. Fix: second-person
  approval for granting roles that hold `sar.view`, plus an alert to the MLRO.
- Legacy `COMPLIANCE_OFFICER` still holds every SAR and rule permission (decision 3 in §11). The demo `compliance` user uses it.


## 14. Sprint 2 log (11 Oct 2026)

**Done**
- **Emergency access** (`app/services/access_control_service.py`, `/api/v1/access/emergency`, migration `0022`):
  an administrator (`emergency.request`) asks for read-only access to one case with a reason and a duration
  (max `EMERGENCY_ACCESS_MAX_MINUTES`, default 240). The MLRO (`sar.grant_access`) approves or rejects; the
  requester cannot approve. Access ends at expiry or when revoked. Every read under a grant writes
  `EMERGENCY_ACCESS` / `VIEW` to the audit log. Grants open the case for reading only (`emergency_read` on GET
  endpoints); no action permission is added.
- **Roles that can see SAR cases need approval:** creating a user with such a role is refused; changing to one
  returns 202 and waits for the MLRO. Neither the requester nor the person receiving the role can approve. The
  "last administrator" rule is checked before the request and again at approval. On a new installation with no
  approver yet, the first such role is granted directly.
- **Deadlines** (`app/services/deadline_service.py`): case SLA days stored on each alert at creation, so policy
  changes do not move running clocks. Escalating with `potential_sar: true` starts the MLRO decision clock and the
  filing deadline from the date of detection. `GET /alerts/{id}/deadlines` shows the case SLA to everyone and the
  SAR clocks only to roles with `sar.view`. The queue's overdue filter now includes missed MLRO decision dates.
- Deadline policy (`CASE_SLA_DAYS`, `SAR_DECISION_DAYS`, `SAR_FILING_DAYS`, `DEADLINE_WARNING_PERCENT`) is
  edited through the existing rule-change maker-checker flow, globally or per jurisdiction.
- Administration → **Access requests** tab for asking, approving and ending access.

**Still for S3**
- Notices at the warning threshold and on breach (needs a notification channel), deadline chips in the queue and
  case page, and a "Potential SAR" option on the escalate dialog (the API supports it).
- Values in `deadline_service.defaults()` are proposals; Compliance must confirm them (decision 4–5 in §11).

## 15. Sprint 3 log (11 Oct 2026)

**Done**
- **SAR confidentiality** (`app/services/sar_confidentiality.py`): a case escalated as a potential SAR stays visible
  to the team, but roles without `sar.view` get it with the escalation notes and reasons, notes written after the
  escalation, summaries written after it and all narratives withheld. Every alert response carries
  `compliance_status` (`IN_PROGRESS` / `WITH_MLRO` / `CLOSED`) and `restricted`; `potential_sar` is returned only to
  roles with `sar.view`. Applied to the alert, list, queue, timeline and customer case-history endpoints.
- **Stored narratives** (`sar_narratives`, migration `0023`): every AI draft and every edit is a new version;
  nothing is overwritten. Once a case is SAR-sensitive, reading, editing, drafting narratives and regenerating the
  summary need `sar.view`.
- **UI:** "Potential SAR" option on the escalate dialog; "Potential SAR" and "With the MLRO · details restricted"
  chips on the case page; SAR decision and filing deadlines in the case header; narrative panel shows the latest
  version and saves new ones; the MLRO's dashboard shows open potential SARs, overdue decisions and filings due
  within 7 days or overdue.

**Changed from the plan**
- No separate `sar.content` permission: `sar.view` already marks exactly the roles that do SAR work, and a second
  permission held by the same roles would add nothing. Revisit if Compliance wants, e.g., auditors to see that a
  SAR exists but not its content.
- No `sar_sensitive` column: `sar_candidate_at` (potential SAR) and `resolution_outcome = SAR_FILED` already say it.
- Breach "notices" are on the MLRO's dashboard; email or chat notifications need a delivery channel KYRO does not
  have yet.

**Next (S4):** AI attestation and wider masking (WS5); phonetic and transliteration screening (WS4).

## 16. Sprint 4 log (11 Oct 2026)

**Done — WS4 screening**
- Names are transliterated (`anyascii`) before matching, common spelling variants are unified, and the list is
  searched by primary name, by alias and by sound (metaphone, `jellyfish`). Migration `0024` adds and backfills
  `alias_text` / `phonetic_text` with trigram indexes; the search runs as three indexed queries (about 15–80 ms per
  name on 20,907 list entries).
- A name that only sounds the same scores `SCREENING_PHONETIC_SCORE` (85), always below the confirmed score, so sound
  alone sends a name to review and never confirms it.
- `SCREENING_CONFIRMED_SCORE`, `SCREENING_POTENTIAL_SCORE`, `SCREENING_PHONETIC_SCORE` are policy, changed through
  maker-checker (`app/services/screening_policy.py`, registered in `policy_registry.py`).

**Done — WS5 AI governance**
- Masking before any AI call now also covers record IDs, street addresses, UK postcodes, US ZIP+4, payment
  references, labelled account and ID numbers, and identifying values from customer and account metadata.
- AI case summaries show "Not checked" until an investigator keeps, corrects or rejects them with the confirmation
  "I have checked this against the source records" (`PUT /alerts/{id}/summary/review`, migration `0025`).
  Narratives are saved only with the same confirmation. The decision is written on the AI call (`human_decision`).
- A SAR cannot be recorded while the latest narrative is an unchecked AI draft.
- `GET /api/v1/ai/oversight`: outputs, accepted, corrected, rejected and unreviewed per prompt version.

**Not done / notes**
- Identifier matching (passport, registration, IMO) and per-list thresholds move to S5 with the re-screen baseline.
- The case report export builds its summary from a template, not from AI text, so it needed no attestation gate.
- Masking errs on the side of hiding: mixed letter-and-digit tokens such as "COVID19" are treated as references.

End-to-end flow, from transaction to resolution: `docs/TRANSACTION_TO_RESOLUTION_WORKFLOW.md`.

## 17. Sprint 5 log (11 Oct 2026)

**Done**
- **Identifiers on watchlist entries:** the OFAC (`idList`), UN (`INDIVIDUAL_DOCUMENT`) and UK OFSI (passport, national
  ID, company and IMO columns) adapters keep passport, national ID, tax, registration and IMO numbers, typed and
  normalised (migration `0026`, GIN-indexed `identifier_values`). OFSI entries are backfilled from stored rows; source
  file hashes are cleared so OFAC and UN are re-read at the next refresh.
- **Identifiers in matching:** customers' identifiers come from their metadata, owners' from
  `identification_type/number`. The same number on both sides finds the entry even under another name (at least a
  potential match) and adds `SCREENING_IDENTIFIER_BOOST`; the same kind of number with a different value takes off
  `SCREENING_IDENTIFIER_PENALTY` and is shown to the analyst as a conflict. Both are policy.
- **Screening baseline:** `GET /api/v1/watchlists/screening-baseline` — a dry run that writes nothing, comparing
  matches with today's policy against matches without phonetic and identifier scoring.

**Not done (carried forward)**
- End-to-end scenario tests across roles (§9) and the gap log they produce.
- Per-list thresholds.

**Next:** rules engine work, planned in `RULES_ENGINE_ENTERPRISE_PLAN.md` and `RULES_ENGINE_IMPLEMENTATION_PHASES.md`.
