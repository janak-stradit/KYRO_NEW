"""
permissions.py — Who may do what in KYRO.

Endpoints ask for a *permission* ("sar.approve"), never for a role name. A
role is a named set of permissions plus a written description of what the
role is for, so roles can be added or adjusted here without touching the
endpoints.

The Administrator runs the system (users, data loads, models, audit) but holds
no case-decision or SAR permission: those sit with the roles accountable for
them, so the most powerful technical account cannot read or decide a SAR.

The role set follows the usual AML operating model (analysts, team lead, QA,
MLRO, rules owner, independent audit, oversight). It is a starting point for
the firm's compliance head to confirm, not a regulatory standard.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Permissions ──────────────────────────────────────────────────────────
PERMISSIONS: dict[str, str] = {
    "cases.view": "See the work queue, cases, customers and documents",
    "cases.view_all": "See every case, not only your own and the unassigned pool",
    "customers.view_all": "See every customer, not only those with a case you can see",
    "sar.view": "See SAR-filed cases, their documents and the fact a SAR was filed",
    "alerts.assign": "Assign alerts to a person",
    "alerts.escalate": "Escalate an alert, or recommend a SAR, to the MLRO",
    "alerts.close_false_positive": "Close an alert as a false positive",
    "alerts.close": "Close an alert as reviewed with no suspicion",
    "sar.approve": "Approve a SAR filing",
    "alerts.qa": "Record a quality check on a resolved case",
    "alerts.baseline": "See false-positive rates by rule",
    "documents.manage": "Upload documents and review the fields read from them",
    "kyc.review": "Schedule and complete KYC reviews",
    "screening.run": "Run watchlist screening on a customer",
    "customers.edit": "Create and update customers, accounts and beneficial owners",
    "transactions.ingest": "Record transactions one at a time or in a batch",
    "ubo.verify": "Verify a beneficial owner",
    "customers.assess_risk": "Recalculate every customer's risk rating",
    "rules.propose": "Propose and backtest rule threshold changes",
    "rules.approve": "Approve or reject rule changes proposed by someone else",
    "rules.edit_direct": "Change a rule threshold immediately, without approval",
    "regulatory.ingest": "Refresh regulations and Federal Register notices",
    "obligations.manage": "Extract, confirm and reject obligations",
    "mappings.manage": "Map obligations to controls",
    "changes.assess": "Assess regulatory changes and notices",
    "feeds.load": "Check and load data feeds",
    "watchlists.ingest": "Refresh sanctions and PEP watchlists",
    "ai.status": "See the AI configuration",
    "ai.admin": "Run the AI connectivity check",
    "ml.train": "Retrain the ML models",
    "audit.read": "Read the audit log",
    "emergency.request": "Ask for time-limited, read-only emergency access to one case",
    "sar.grant_access": "Approve emergency access to a case, or a role that can see SAR cases",
    "assignment.manage": "Set up teams and the rules that assign new alerts to them",
    "users.manage": "Create users and assign roles",
}


@dataclass(frozen=True)
class RoleDefinition:
    code: str
    label: str
    purpose: str
    responsibilities: tuple[str, ...]
    limits: tuple[str, ...]
    permissions: frozenset[str] = field(default_factory=frozenset)
    read_only: bool = False   # may not change anything, whatever the endpoint
    legacy: bool = False      # kept for existing users; prefer the specific roles


def _role(code, label, purpose, responsibilities, limits, permissions, **flags) -> RoleDefinition:
    unknown = set(permissions) - set(PERMISSIONS)
    assert not unknown, f"{code}: unknown permissions {unknown}"
    return RoleDefinition(code, label, purpose, tuple(responsibilities), tuple(limits), frozenset(permissions), **flags)


_VIEW = {"cases.view"}
_ALL_RECORDS = {"cases.view_all", "customers.view_all"}
# Deciding a case, filing a SAR or changing a rule: never part of the system administrator's role
DECISION_PERMISSIONS = frozenset({
    "sar.view", "sar.approve", "alerts.assign", "alerts.escalate", "alerts.close_false_positive", "alerts.close", "alerts.qa",
    "rules.propose", "rules.approve", "rules.edit_direct", "obligations.manage", "mappings.manage", "changes.assess",
    "kyc.review", "screening.run", "customers.edit", "ubo.verify", "customers.assess_risk", "documents.manage",
    "sar.grant_access", "assignment.manage",
})

ROLE_DEFINITIONS: tuple[RoleDefinition, ...] = (
    _role(
        "ADMIN", "Administrator", "Runs the system: users, data loads, models and the audit log.",
        ["Create users and assign roles", "Load data feeds, transactions, watchlists and regulations",
         "Retrain models and check the AI connection", "Read the audit log",
         "Ask for time-limited, read-only emergency access to a case, approved by the MLRO"],
        ["Cannot see SAR-filed cases or approve a SAR", "Cannot resolve, escalate, assign or quality-check cases",
         "Cannot change customer records, documents or rules",
         "Cannot give anyone a role that sees SAR cases without the MLRO's approval"],
        set(PERMISSIONS) - DECISION_PERMISSIONS,
    ),
    _role(
        "MLRO", "MLRO / AML Officer", "The accountable AML officer: final say on suspicion and on the programme's rules.",
        ["Approve SAR filings", "Close or return escalated cases", "Approve rule changes and confirm obligations",
         "Assess regulatory changes", "Assign work and quality-check cases",
         "Approve emergency access and roles that can see SAR cases"],
        ["Cannot approve a rule change they proposed", "Cannot manage users or system settings"],
        _VIEW | _ALL_RECORDS | {"sar.view", "sar.approve", "alerts.close", "alerts.close_false_positive", "alerts.escalate", "alerts.assign", "alerts.qa",
                 "alerts.baseline", "documents.manage", "kyc.review", "screening.run", "customers.edit", "ubo.verify", "customers.assess_risk",
                 "rules.propose", "rules.approve", "regulatory.ingest", "obligations.manage", "mappings.manage", "changes.assess",
                 "audit.read", "ai.status", "sar.grant_access", "assignment.manage"},
    ),
    _role(
        "TEAM_LEAD", "Team Lead", "Runs the alert queue day to day.",
        ["Assign alerts", "Close ordinary cases", "Escalate suspicion to the MLRO", "Complete KYC reviews",
         "Set up teams and the rules that assign new alerts"],
        ["Cannot approve a SAR or see SAR-filed cases", "Cannot change rules"],
        _VIEW | _ALL_RECORDS | {"alerts.assign", "alerts.close", "alerts.close_false_positive", "alerts.escalate", "alerts.baseline",
                 "documents.manage", "kyc.review", "screening.run", "customers.edit", "ubo.verify", "assignment.manage"},
    ),
    _role(
        "L2_INVESTIGATOR", "Level 2 Investigator", "Investigates escalated cases in depth.",
        ["Investigate and document findings", "Close a case with no suspicion", "Recommend a SAR by escalating to the MLRO",
         "Upload and review documents", "Correct customer details from documents"],
        ["Sees only cases assigned to them and the unassigned pool", "Cannot approve a SAR or see SAR-filed cases",
         "Cannot assign work or change rules"],
        _VIEW | {"alerts.close", "alerts.close_false_positive", "alerts.escalate", "documents.manage", "screening.run", "customers.edit"},
    ),
    _role(
        "L1_ANALYST", "Level 1 Analyst", "First look at every alert.",
        ["Close an obvious false positive, with a reason", "Escalate anything else"],
        ["Sees only cases assigned to them and the unassigned pool", "Cannot close a true positive or recommend a SAR",
         "Cannot see SAR-filed cases", "Cannot change customer records, documents or rules"],
        _VIEW | {"alerts.close_false_positive", "alerts.escalate"},
    ),
    _role(
        "KYC_ANALYST", "KYC Analyst", "Keeps customer due diligence current.",
        ["Complete periodic reviews and set the rating after review", "Run screening and review matches",
         "Collect and check customer documents", "Escalate concerns found during a review"],
        ["Sees only cases assigned to them and the unassigned pool, but every customer", "Cannot resolve transaction alerts",
         "Cannot see SAR-filed cases", "Cannot change rules"],
        _VIEW | {"customers.view_all", "kyc.review", "screening.run", "documents.manage", "customers.edit", "ubo.verify", "alerts.escalate"},
    ),
    _role(
        "QA_REVIEWER", "QA Reviewer", "Checks that closed cases followed policy.",
        ["Sample resolved cases and record pass or fail with notes", "Read the audit trail"],
        ["Cannot change a case's outcome", "Cannot check a case they resolved", "Cannot see SAR-filed cases"],
        _VIEW | _ALL_RECORDS | {"alerts.qa", "alerts.baseline", "audit.read"},
    ),
    _role(
        "RULES_OWNER", "Rules Owner", "Maintains detection rules and their link to regulation.",
        ["Propose threshold changes with a backtest", "Extract and confirm obligations", "Map obligations to controls",
         "Refresh regulatory sources"],
        ["Cannot approve their own rule changes", "Cannot resolve cases", "Cannot see SAR-filed cases"],
        _VIEW | _ALL_RECORDS | {"rules.propose", "obligations.manage", "mappings.manage", "regulatory.ingest", "alerts.baseline", "ai.status"},
    ),
    _role(
        "AUDITOR", "Auditor", "Independent testing of the AML programme.",
        ["Read everything, including the audit log"],
        ["Cannot change any record"],
        _VIEW | _ALL_RECORDS | {"sar.view", "audit.read", "alerts.baseline"},
        read_only=True,
    ),
    _role(
        "EXECUTIVE_VIEWER", "Executive Viewer", "Senior management oversight.",
        ["See dashboards and summary figures"],
        ["Cannot open cases, customers or documents", "Cannot change any record"],
        set(),
        read_only=True,
    ),
    # Existing roles, unchanged in what they can do
    _role(
        "COMPLIANCE_OFFICER", "Compliance Officer (legacy)", "The original combined compliance role.",
        ["Everything the MLRO, Team Lead and Rules Owner can do, plus loading data feeds and direct rule edits"],
        ["Cannot manage users, retrain models or run the AI connectivity check"],
        set(PERMISSIONS) - {"users.manage", "ml.train", "ai.admin"},
        legacy=True,
    ),
    _role(
        "ANALYST", "Analyst (legacy)", "The original analyst role.",
        ["Assign and escalate alerts", "Documents, KYC reviews, screening and customer updates", "Record transactions"],
        ["Sees only cases assigned to them and the unassigned pool, but every customer", "Cannot resolve alerts or see SAR-filed cases",
         "Cannot change rules"],
        _VIEW | {"customers.view_all", "alerts.assign", "alerts.escalate", "documents.manage", "kyc.review", "screening.run",
                 "customers.edit", "transactions.ingest"},
        legacy=True,
    ),
)

ROLES: dict[str, RoleDefinition] = {r.code: r for r in ROLE_DEFINITIONS}
ROLE_CODES: tuple[str, ...] = tuple(ROLES)


def permissions_for(role: str) -> frozenset[str]:
    definition = ROLES.get(role)
    return definition.permissions if definition else frozenset()


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def is_read_only(role: str) -> bool:
    definition = ROLES.get(role)
    return definition is None or definition.read_only
