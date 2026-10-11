"""
services/rules_engine.py — R001-R010 transaction risk rules.

Each rule inspects a transaction (plus its owning customer and recent
transaction history) and, if triggered, contributes a severity-weighted
score. Scores are summed and capped at 100; an Alert is opened when the
total crosses ALERT_THRESHOLD or any CRITICAL rule fires.

Rules engine R1 (RuleOptions, switched on in settings after a replay review):
amounts compared in the base currency; no per-payment PEP/sanctions hits;
weak indicators need a substantive rule; R010 looks back only; one open rules
alert per customer per day. Every alert records the rule version, the values
used and its evidence transactions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction, TransactionRiskFlag
from app.services.audit_service import log_action
from app.services.rule_config_service import get_effective_config

# Hardcoded fallback values. These stay importable as module attributes
# (app/ml/features/engineer.py and app/ml/training/trainer.py both import
# HIGH_RISK_COUNTRIES / ALERT_THRESHOLD directly, as a static snapshot for
# offline batch feature engineering / training) and double as the last-resort
# defaults get_effective_config() falls back to when a key has no DB row —
# e.g. against a fresh database before any RuleConfig has been seeded.
AMOUNT_THRESHOLD = 10_000
VELOCITY_DAILY_LIMIT = 5
VELOCITY_HOURLY_LIMIT = 3
RAPID_SUCCESSION_WINDOW_SECONDS = 60
ALERT_THRESHOLD = 50
EDD_THRESHOLD = 75

# Illustrative FATF-style high-risk/sanctioned jurisdiction list; extend as needed.
HIGH_RISK_COUNTRIES = {
    "IR", "KP", "SY", "MM", "AF", "YE", "SS",
    "IRAN", "NORTH KOREA", "SYRIA", "MYANMAR", "AFGHANISTAN", "YEMEN",
}

SEVERITY_WEIGHT = {"LOW": 10, "MEDIUM": 25, "HIGH": 50, "CRITICAL": 90}

# Compliance-editable via /api/v1/rule-configs (see rule_config_service.py).
# Keys here are exactly what a RuleConfig.key must match to take effect.
DEFAULTS: dict = {
    "AMOUNT_THRESHOLD": AMOUNT_THRESHOLD,
    "VELOCITY_DAILY_LIMIT": VELOCITY_DAILY_LIMIT,
    "VELOCITY_HOURLY_LIMIT": VELOCITY_HOURLY_LIMIT,
    "RAPID_SUCCESSION_WINDOW_SECONDS": RAPID_SUCCESSION_WINDOW_SECONDS,
    "ALERT_THRESHOLD": ALERT_THRESHOLD,
    "EDD_THRESHOLD": EDD_THRESHOLD,
    "HIGH_RISK_COUNTRIES": sorted(HIGH_RISK_COUNTRIES),
    "SEVERITY_WEIGHT": dict(SEVERITY_WEIGHT),
}


def resolve_config(db: Session, customer: Customer) -> dict:
    jurisdiction = customer.residency_country or customer.country
    return get_effective_config(db, DEFAULTS, jurisdiction)


# Indicators that are not suspicious on their own: with noise reduction on they count
# only when a substantive rule also fired (docs/plans/RULES_ENGINE_ENTERPRISE_PLAN.md §2)
WEAK_RULES = frozenset({"R007", "R008", "R009"})
SANCTIONS_CASE_RULE = "SANCTIONS_CUSTOMER"


@dataclass(frozen=True)
class RuleOptions:
    """The R1 switches (settings.rules_*). Replay passes its own to compare before and after."""

    base_currency: bool = False
    noise_reduction: bool = False
    consolidate_daily: bool = False

    @classmethod
    def from_settings(cls) -> "RuleOptions":
        s = get_settings()
        return cls(s.rules_base_currency_enabled, s.rules_noise_reduction_enabled, s.rules_consolidate_daily)

    def signature(self) -> str:
        """Which scoring the engine applies; stored with ML models trained on its scores."""
        return f"legacy-r1;base_ccy={int(self.base_currency)};noise={int(self.noise_reduction)}"


def rule_version(cfg: dict, options: RuleOptions) -> str:
    """A short hash of the effective configuration and switches: equal versions alert identically."""
    payload = json.dumps({"cfg": cfg, "options": asdict(options)}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class TriggeredRule:
    rule_id: str
    name: str
    description: str
    severity: str


def _is_high_risk_country(high_risk_countries: set[str], *countries: str | None) -> bool:
    return any(c and c.strip().upper() in high_risk_countries for c in countries)


def evaluate(
    db: Session, txn: Transaction, customer: Customer, cfg: dict | None = None, options: RuleOptions | None = None,
) -> list[TriggeredRule]:
    if cfg is None:
        cfg = resolve_config(db, customer)
    options = options or RuleOptions.from_settings()

    amount_threshold = cfg["AMOUNT_THRESHOLD"]
    velocity_daily_limit = cfg["VELOCITY_DAILY_LIMIT"]
    velocity_hourly_limit = cfg["VELOCITY_HOURLY_LIMIT"]
    rapid_succession_window_seconds = cfg["RAPID_SUCCESSION_WINDOW_SECONDS"]
    high_risk_countries = set(cfg["HIGH_RISK_COUNTRIES"])

    triggered: list[TriggeredRule] = []

    # R001 — Amount Threshold, in the base currency when switched on and a rate is known
    if options.base_currency and txn.amount_base is not None:
        if float(txn.amount_base) > amount_threshold:
            triggered.append(TriggeredRule(
                "R001", "Amount Threshold",
                f"Transaction {txn.amount} {txn.currency} ({txn.amount_base} {get_settings().base_currency}) > {amount_threshold}", "MEDIUM",
            ))
    elif txn.amount > amount_threshold:
        triggered.append(TriggeredRule("R001", "Amount Threshold", f"Transaction {txn.amount} > {amount_threshold}", "MEDIUM"))

    # R002 — Velocity Daily
    daily_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.customer_id == txn.customer_id,
            Transaction.transaction_date >= txn.transaction_date - timedelta(days=1),
            Transaction.transaction_date <= txn.transaction_date,
            Transaction.id != txn.id,
        )
        .scalar()
        or 0
    ) + 1
    if daily_count > velocity_daily_limit:
        triggered.append(TriggeredRule("R002", "Velocity Daily", f"{daily_count} transactions/day > {velocity_daily_limit}", "MEDIUM"))

    # R003 — Velocity Hourly
    hourly_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.customer_id == txn.customer_id,
            Transaction.transaction_date >= txn.transaction_date - timedelta(hours=1),
            Transaction.transaction_date <= txn.transaction_date,
            Transaction.id != txn.id,
        )
        .scalar()
        or 0
    ) + 1
    if hourly_count > velocity_hourly_limit:
        triggered.append(TriggeredRule("R003", "Velocity Hourly", f"{hourly_count} transactions/hour > {velocity_hourly_limit}", "LOW"))

    # R004 — High Risk Country
    if _is_high_risk_country(high_risk_countries, txn.meta_country, txn.meta_destination_country, txn.meta_origin_country):
        triggered.append(TriggeredRule("R004", "High Risk Country", "Counterparty in sanctioned/high-risk country", "HIGH"))

    # R005 / R006 describe the customer, not the payment. With noise reduction on they are not
    # raised on every transaction: PEP status weighs in the customer's rating, and a confirmed
    # sanctions match opens one customer case (open_sanctions_case).

    # R005 — PEP Match
    if customer.pep_flag and not options.noise_reduction:
        triggered.append(TriggeredRule("R005", "PEP Match", "Customer is a Politically Exposed Person", "HIGH"))

    # R006 — Sanctions Match
    if customer.sanctions_flag and not options.noise_reduction:
        triggered.append(TriggeredRule("R006", "Sanctions Match", "Customer matched on a sanctions list", "CRITICAL"))

    # R007 — New Counterparty
    if txn.meta_counterparty:
        prior = (
            db.query(func.count(Transaction.id))
            .filter(
                Transaction.customer_id == txn.customer_id,
                Transaction.meta_counterparty == txn.meta_counterparty,
                Transaction.id != txn.id,
            )
            .scalar()
            or 0
        )
        if prior == 0:
            triggered.append(TriggeredRule("R007", "New Counterparty", f"First-time counterparty: {txn.meta_counterparty}", "LOW"))

    # R008 — Weekend Activity
    if txn.transaction_date.weekday() >= 5:
        triggered.append(TriggeredRule("R008", "Weekend Activity", "Transaction occurred on a weekend", "LOW"))

    # R009 — Round Amount
    if txn.amount >= 1000 and float(txn.amount) % 1000 == 0:
        triggered.append(TriggeredRule("R009", "Round Amount", f"Suspicious round amount: {txn.amount}", "MEDIUM"))

    # R010 — Rapid Succession
    recent = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.customer_id == txn.customer_id,
            Transaction.id != txn.id,
            Transaction.transaction_date >= txn.transaction_date - timedelta(seconds=rapid_succession_window_seconds),
            # Earlier transactions only once noise reduction is on: a batch file loaded in one go is not rapid succession
            Transaction.transaction_date <= txn.transaction_date
            + timedelta(seconds=0 if options.noise_reduction else rapid_succession_window_seconds),
        )
        .scalar()
        or 0
    )
    if recent > 0:
        triggered.append(TriggeredRule("R010", "Rapid Succession", "Multiple transactions within 1 minute", "HIGH"))

    return triggered


def score_from_rules(rules: list[TriggeredRule], severity_weights: dict[str, int] | None = None) -> int:
    weights = severity_weights if severity_weights is not None else SEVERITY_WEIGHT
    return min(100, sum(weights[r.severity] for r in rules))


def recommended_action_for(
    rules: list[TriggeredRule],
    score: int,
    alert_threshold: int | None = None,
    edd_threshold: int | None = None,
) -> str | None:
    alert_threshold = ALERT_THRESHOLD if alert_threshold is None else alert_threshold
    edd_threshold = EDD_THRESHOLD if edd_threshold is None else edd_threshold
    if any(r.severity == "CRITICAL" for r in rules):
        return "SAR"
    if score >= edd_threshold:
        return "ENHANCED_DUE_DILIGENCE"
    if score >= alert_threshold:
        return "REVIEW"
    return None


def apply_to_transaction(db: Session, txn: Transaction, customer: Customer) -> tuple[list[TriggeredRule], int, Alert | None]:
    """Run all rules against a transaction, persist risk flags, update the
    transaction's risk_score/risk_flags, and open an Alert if warranted."""
    cfg = resolve_config(db, customer)
    options = RuleOptions.from_settings()
    from app.services import fx_service  # imported here to avoid an import cycle

    conversion = fx_service.apply(db, txn)
    rules = evaluate(db, txn, customer, cfg=cfg, options=options)
    score = score_from_rules(rules, severity_weights=cfg["SEVERITY_WEIGHT"])

    txn.risk_score = score
    txn.risk_flags = {"triggered_rules": [r.rule_id for r in rules]}

    for rule in rules:
        db.add(
            TransactionRiskFlag(
                transaction_id=txn.id,
                flag_type=rule.rule_id,
                flag_description=f"{rule.name}: {rule.description}",
                flag_severity=rule.severity,
            )
        )

    alert: Alert | None = None
    action = recommended_action_for(rules, score, alert_threshold=cfg["ALERT_THRESHOLD"], edd_threshold=cfg["EDD_THRESHOLD"])
    if options.noise_reduction and not any(r.rule_id not in WEAK_RULES for r in rules):
        action = None  # weak indicators alone do not open an alert
    parameters = {
        "thresholds": {k: cfg[k] for k in ("AMOUNT_THRESHOLD", "ALERT_THRESHOLD", "EDD_THRESHOLD", "VELOCITY_DAILY_LIMIT",
                                           "VELOCITY_HOURLY_LIMIT", "RAPID_SUCCESSION_WINDOW_SECONDS")},
        "options": asdict(options),
        "rules": [{"rule": r.rule_id, "description": r.description, "severity": r.severity} for r in rules],
        "amount": float(txn.amount), "currency": txn.currency, "base_currency": get_settings().base_currency,
        "amount_base": float(conversion.amount_base) if conversion.amount_base is not None else None,
        "fx_rate": float(conversion.rate) if conversion.rate is not None else None,
        "fx_stale": conversion.stale, "fx_missing": conversion.missing,
    }
    version = rule_version(cfg, options)
    if action is not None and options.consolidate_daily:
        alert = _consolidate(db, customer, txn, rules, score, action, parameters, version)
        if alert is not None:
            db.flush()
            from app.services import customer_risk_service  # imported here to avoid an import cycle

            customer_risk_service.assess_customer(db, customer)
            return rules, score, alert
    if action is not None:
        alert = Alert(
            customer_id=customer.id,
            alert_type="BEHAVIORAL_ANOMALY" if not any(r.rule_id in ("R005", "R006") for r in rules) else "SANCTIONS" if any(r.rule_id == "R006" for r in rules) else "PEP",
            risk_score=score,
            confidence=min(100.0, score * 1.0),
            triggered_rules={"rules": [r.rule_id for r in rules]},
            recommended_action=action,
            status="OPEN",
            rule_version=version,
            parameters=parameters,
            evidence_transaction_ids=[txn.id],
        )
        db.add(alert)

    db.flush()
    if alert is not None:
        from app.services import customer_risk_service, deadline_service  # imported here to avoid an import cycle

        deadline_service.start_case_clock(db, alert, customer)
        # A new alert can change the customer's rating

        customer_risk_service.assess_customer(db, customer)
    return rules, score, alert


_ACTION_RANK = {None: 0, "REVIEW": 1, "ENHANCED_DUE_DILIGENCE": 2, "SAR": 3}


def _consolidate(
    db: Session, customer: Customer, txn: Transaction, rules: list[TriggeredRule], score: int, action: str,
    parameters: dict, version: str,
) -> Alert | None:
    """Add this transaction to the customer's open rules alert from today, if there is one."""
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    alert = (
        db.query(Alert)
        .filter(
            Alert.customer_id == customer.id, Alert.status.in_(("OPEN", "ASSIGNED", "IN_REVIEW")),
            Alert.triggered_rules.isnot(None), Alert.created_at >= start_of_day,
        )
        .order_by(Alert.created_at.desc())
        .with_for_update()
        .first()
    )
    if alert is None:
        return None
    existing = list((alert.triggered_rules or {}).get("rules") or [])
    alert.triggered_rules = {"rules": existing + [r.rule_id for r in rules if r.rule_id not in existing]}
    alert.risk_score = max(alert.risk_score, score)
    if _ACTION_RANK.get(action, 0) > _ACTION_RANK.get(alert.recommended_action, 0):
        alert.recommended_action = action
    alert.evidence_transaction_ids = [*(alert.evidence_transaction_ids or []), txn.id]
    alert.parameters = {**(alert.parameters or {}), "consolidated": [*((alert.parameters or {}).get("consolidated") or []),
                                                                      {"transaction_id": str(txn.id), **parameters}]}
    alert.rule_version = version
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="UPDATE",
               new_values={"consolidated_transaction": str(txn.id), "rules": [r.rule_id for r in rules]})
    return alert


def open_sanctions_case(db: Session, customer: Customer, reason: str) -> Alert | None:
    """
    With noise reduction on, a customer newly confirmed as sanctioned gets one case, instead of an
    R006 alert on every payment. Does nothing if such a case is already open, or if the switch is off
    (R006 then alerts per payment as before).
    """
    if not RuleOptions.from_settings().noise_reduction:
        return None
    open_case = db.query(Alert.id).filter(
        Alert.customer_id == customer.id, Alert.status.in_(("OPEN", "ASSIGNED", "IN_REVIEW", "ESCALATED")),
        Alert.triggered_rules["rules"].contains([SANCTIONS_CASE_RULE]),
    ).first()
    if open_case is not None:
        return None
    alert = Alert(
        customer_id=customer.id, alert_type="SANCTIONS", risk_score=100, confidence=100.0,
        triggered_rules={"rules": [SANCTIONS_CASE_RULE]}, recommended_action="IMMEDIATE_REVIEW", status="OPEN",
        parameters={"reason": reason}, rule_version="sanctions-case-v1",
    )
    db.add(alert)
    db.flush()
    from app.services import customer_risk_service, deadline_service  # imported here to avoid an import cycle

    deadline_service.start_case_clock(db, alert, customer)
    customer_risk_service.assess_customer(db, customer)
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="CREATE", new_values={"sanctions_case": reason})
    return alert
