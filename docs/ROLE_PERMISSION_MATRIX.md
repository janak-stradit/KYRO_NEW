# KYRO Role Permission Matrix

Generated from `app/permissions.py` by `scripts/role_matrix.py`. Do not edit by hand.

✔ = the role holds the permission. Read-only roles cannot change any record whatever they hold.

## Visibility rules (app/visibility.py)

- Without `cases.view_all` a role sees only cases assigned to it and the unassigned pool.
- Without `customers.view_all` a role sees only customers that have such a case.
- A SAR-filed case, its documents and the fact a SAR was filed are visible only with `sar.view`; to anyone else they do not exist (404).
- Every opening of a SAR-filed case is written to the audit log (`SAR` / `VIEW`).
- A case escalated as a potential SAR stays visible, but without `sar.view` its escalation notes and reasons, later notes, later summaries and narratives are withheld; its progress shows as a general status (In progress / With the MLRO / Closed).
- An approved emergency access grant lets one user read one case for a limited time; each use is audited (`EMERGENCY_ACCESS` / `VIEW`).

## Matrix

### Cases and alerts

| Permission | ADMIN | MLRO | TEAM_LEAD | L2_INVESTIGATOR | L1_ANALYST | KYC_ANALYST | QA_REVIEWER | RULES_OWNER | AUDITOR | EXECUTIVE_VIEWER | COMPLIANCE_OFFICER | ANALYST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `cases.view` — See the work queue, cases, customers and documents | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |  | ✔ | ✔ |
| `cases.view_all` — See every case, not only your own and the unassigned pool | ✔ | ✔ | ✔ |  |  |  | ✔ | ✔ | ✔ |  | ✔ |  |
| `alerts.assign` — Assign alerts to a person |  | ✔ | ✔ |  |  |  |  |  |  |  | ✔ | ✔ |
| `assignment.manage` — Set up teams and the rules that assign new alerts to them |  | ✔ | ✔ |  |  |  |  |  |  |  | ✔ |  |
| `alerts.close_false_positive` — Close an alert as a false positive |  | ✔ | ✔ | ✔ | ✔ |  |  |  |  |  | ✔ |  |
| `alerts.close` — Close an alert as reviewed with no suspicion |  | ✔ | ✔ | ✔ |  |  |  |  |  |  | ✔ |  |
| `alerts.escalate` — Escalate an alert, or recommend a SAR, to the MLRO |  | ✔ | ✔ | ✔ | ✔ | ✔ |  |  |  |  | ✔ | ✔ |
| `alerts.qa` — Record a quality check on a resolved case |  | ✔ |  |  |  |  | ✔ |  |  |  | ✔ |  |
| `alerts.baseline` — See false-positive rates by rule | ✔ | ✔ | ✔ |  |  |  | ✔ | ✔ | ✔ |  | ✔ |  |

### SAR

| Permission | ADMIN | MLRO | TEAM_LEAD | L2_INVESTIGATOR | L1_ANALYST | KYC_ANALYST | QA_REVIEWER | RULES_OWNER | AUDITOR | EXECUTIVE_VIEWER | COMPLIANCE_OFFICER | ANALYST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sar.view` — See SAR-filed cases, their documents and the fact a SAR was filed |  | ✔ |  |  |  |  |  |  | ✔ |  | ✔ |  |
| `sar.approve` — Approve a SAR filing |  | ✔ |  |  |  |  |  |  |  |  | ✔ |  |
| `sar.grant_access` — Approve emergency access to a case, or a role that can see SAR cases |  | ✔ |  |  |  |  |  |  |  |  | ✔ |  |
| `emergency.request` — Ask for time-limited, read-only emergency access to one case | ✔ |  |  |  |  |  |  |  |  |  | ✔ |  |

### Customers and KYC

| Permission | ADMIN | MLRO | TEAM_LEAD | L2_INVESTIGATOR | L1_ANALYST | KYC_ANALYST | QA_REVIEWER | RULES_OWNER | AUDITOR | EXECUTIVE_VIEWER | COMPLIANCE_OFFICER | ANALYST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `customers.view_all` — See every customer, not only those with a case you can see | ✔ | ✔ | ✔ |  |  | ✔ | ✔ | ✔ | ✔ |  | ✔ | ✔ |
| `customers.edit` — Create and update customers, accounts and beneficial owners |  | ✔ | ✔ | ✔ |  | ✔ |  |  |  |  | ✔ | ✔ |
| `customers.assess_risk` — Recalculate every customer's risk rating |  | ✔ |  |  |  |  |  |  |  |  | ✔ |  |
| `kyc.review` — Schedule and complete KYC reviews |  | ✔ | ✔ |  |  | ✔ |  |  |  |  | ✔ | ✔ |
| `screening.run` — Run watchlist screening on a customer |  | ✔ | ✔ | ✔ |  | ✔ |  |  |  |  | ✔ | ✔ |
| `ubo.verify` — Verify a beneficial owner |  | ✔ | ✔ |  |  | ✔ |  |  |  |  | ✔ |  |
| `documents.manage` — Upload documents and review the fields read from them |  | ✔ | ✔ | ✔ |  | ✔ |  |  |  |  | ✔ | ✔ |

### Rules and regulation

| Permission | ADMIN | MLRO | TEAM_LEAD | L2_INVESTIGATOR | L1_ANALYST | KYC_ANALYST | QA_REVIEWER | RULES_OWNER | AUDITOR | EXECUTIVE_VIEWER | COMPLIANCE_OFFICER | ANALYST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `rules.propose` — Propose and backtest rule threshold changes |  | ✔ |  |  |  |  |  | ✔ |  |  | ✔ |  |
| `rules.approve` — Approve or reject rule changes proposed by someone else |  | ✔ |  |  |  |  |  |  |  |  | ✔ |  |
| `rules.edit_direct` — Change a rule threshold immediately, without approval |  |  |  |  |  |  |  |  |  |  | ✔ |  |
| `regulatory.ingest` — Refresh regulations and Federal Register notices | ✔ | ✔ |  |  |  |  |  | ✔ |  |  | ✔ |  |
| `obligations.manage` — Extract, confirm and reject obligations |  | ✔ |  |  |  |  |  | ✔ |  |  | ✔ |  |
| `mappings.manage` — Map obligations to controls |  | ✔ |  |  |  |  |  | ✔ |  |  | ✔ |  |
| `changes.assess` — Assess regulatory changes and notices |  | ✔ |  |  |  |  |  |  |  |  | ✔ |  |

### Data and system

| Permission | ADMIN | MLRO | TEAM_LEAD | L2_INVESTIGATOR | L1_ANALYST | KYC_ANALYST | QA_REVIEWER | RULES_OWNER | AUDITOR | EXECUTIVE_VIEWER | COMPLIANCE_OFFICER | ANALYST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `transactions.ingest` — Record transactions one at a time or in a batch | ✔ |  |  |  |  |  |  |  |  |  | ✔ | ✔ |
| `feeds.load` — Check and load data feeds | ✔ |  |  |  |  |  |  |  |  |  | ✔ |  |
| `watchlists.ingest` — Refresh sanctions and PEP watchlists | ✔ |  |  |  |  |  |  |  |  |  | ✔ |  |
| `ml.train` — Retrain the ML models | ✔ |  |  |  |  |  |  |  |  |  |  |  |
| `ai.status` — See the AI configuration | ✔ | ✔ |  |  |  |  |  | ✔ |  |  | ✔ |  |
| `ai.admin` — Run the AI connectivity check | ✔ |  |  |  |  |  |  |  |  |  |  |  |
| `audit.read` — Read the audit log | ✔ | ✔ |  |  |  |  | ✔ |  | ✔ |  | ✔ |  |
| `users.manage` — Create users and assign roles | ✔ |  |  |  |  |  |  |  |  |  |  |  |

## Roles

### Administrator (`ADMIN`)

Runs the system: users, data loads, models and the audit log.

**Does:**
- Create users and assign roles
- Load data feeds, transactions, watchlists and regulations
- Retrain models and check the AI connection
- Read the audit log
- Ask for time-limited, read-only emergency access to a case, approved by the MLRO

**Cannot:**
- Cannot see SAR-filed cases or approve a SAR
- Cannot resolve, escalate, assign or quality-check cases
- Cannot change customer records, documents or rules
- Cannot give anyone a role that sees SAR cases without the MLRO's approval

### MLRO / AML Officer (`MLRO`)

The accountable AML officer: final say on suspicion and on the programme's rules.

**Does:**
- Approve SAR filings
- Close or return escalated cases
- Approve rule changes and confirm obligations
- Assess regulatory changes
- Assign work and quality-check cases
- Approve emergency access and roles that can see SAR cases

**Cannot:**
- Cannot approve a rule change they proposed
- Cannot manage users or system settings

### Team Lead (`TEAM_LEAD`)

Runs the alert queue day to day.

**Does:**
- Assign alerts
- Close ordinary cases
- Escalate suspicion to the MLRO
- Complete KYC reviews
- Set up teams and the rules that assign new alerts

**Cannot:**
- Cannot approve a SAR or see SAR-filed cases
- Cannot change rules

### Level 2 Investigator (`L2_INVESTIGATOR`)

Investigates escalated cases in depth.

**Does:**
- Investigate and document findings
- Close a case with no suspicion
- Recommend a SAR by escalating to the MLRO
- Upload and review documents
- Correct customer details from documents

**Cannot:**
- Sees only cases assigned to them and the unassigned pool
- Cannot approve a SAR or see SAR-filed cases
- Cannot assign work or change rules

### Level 1 Analyst (`L1_ANALYST`)

First look at every alert.

**Does:**
- Close an obvious false positive, with a reason
- Escalate anything else

**Cannot:**
- Sees only cases assigned to them and the unassigned pool
- Cannot close a true positive or recommend a SAR
- Cannot see SAR-filed cases
- Cannot change customer records, documents or rules

### KYC Analyst (`KYC_ANALYST`)

Keeps customer due diligence current.

**Does:**
- Complete periodic reviews and set the rating after review
- Run screening and review matches
- Collect and check customer documents
- Escalate concerns found during a review

**Cannot:**
- Sees only cases assigned to them and the unassigned pool, but every customer
- Cannot resolve transaction alerts
- Cannot see SAR-filed cases
- Cannot change rules

### QA Reviewer (`QA_REVIEWER`)

Checks that closed cases followed policy.

**Does:**
- Sample resolved cases and record pass or fail with notes
- Read the audit trail

**Cannot:**
- Cannot change a case's outcome
- Cannot check a case they resolved
- Cannot see SAR-filed cases

### Rules Owner (`RULES_OWNER`)

Maintains detection rules and their link to regulation.

**Does:**
- Propose threshold changes with a backtest
- Extract and confirm obligations
- Map obligations to controls
- Refresh regulatory sources

**Cannot:**
- Cannot approve their own rule changes
- Cannot resolve cases
- Cannot see SAR-filed cases

### Auditor (`AUDITOR`) — read-only

Independent testing of the AML programme.

**Does:**
- Read everything, including the audit log

**Cannot:**
- Cannot change any record

### Executive Viewer (`EXECUTIVE_VIEWER`) — read-only

Senior management oversight.

**Does:**
- See dashboards and summary figures

**Cannot:**
- Cannot open cases, customers or documents
- Cannot change any record

### Compliance Officer (legacy) (`COMPLIANCE_OFFICER`) — legacy

The original combined compliance role.

**Does:**
- Everything the MLRO, Team Lead and Rules Owner can do, plus loading data feeds and direct rule edits

**Cannot:**
- Cannot manage users, retrain models or run the AI connectivity check

### Analyst (legacy) (`ANALYST`) — legacy

The original analyst role.

**Does:**
- Assign and escalate alerts
- Documents, KYC reviews, screening and customer updates
- Record transactions

**Cannot:**
- Sees only cases assigned to them and the unassigned pool, but every customer
- Cannot resolve alerts or see SAR-filed cases
- Cannot change rules
