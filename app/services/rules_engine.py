"""
services/rules_engine.py — R001-R010 transaction risk rules.

Each rule inspects a transaction (plus its owning customer and recent
transaction history) and, if triggered, contributes a severity-weighted
score. Scores are summed and capped at 100; an Alert is opened when the
total crosses ALERT_THRESHOLD or any CRITICAL rule fires.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction, TransactionRiskFlag
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


@dataclass
class TriggeredRule:
    rule_id: str
    name: str
    description: str
    severity: str


def _is_high_risk_country(high_risk_countries: set[str], *countries: str | None) -> bool:
    return any(c and c.strip().upper() in high_risk_countries for c in countries)


def evaluate(db: Session, txn: Transaction, customer: Customer, cfg: dict | None = None) -> list[TriggeredRule]:
    if cfg is None:
        cfg = resolve_config(db, customer)

    amount_threshold = cfg["AMOUNT_THRESHOLD"]
    velocity_daily_limit = cfg["VELOCITY_DAILY_LIMIT"]
    velocity_hourly_limit = cfg["VELOCITY_HOURLY_LIMIT"]
    rapid_succession_window_seconds = cfg["RAPID_SUCCESSION_WINDOW_SECONDS"]
    high_risk_countries = set(cfg["HIGH_RISK_COUNTRIES"])

    triggered: list[TriggeredRule] = []

    # R001 — Amount Threshold
    if txn.amount > amount_threshold:
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

    # R005 — PEP Match
    if customer.pep_flag:
        triggered.append(TriggeredRule("R005", "PEP Match", "Customer is a Politically Exposed Person", "HIGH"))

    # R006 — Sanctions Match
    if customer.sanctions_flag:
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
            Transaction.transaction_date <= txn.transaction_date + timedelta(seconds=rapid_succession_window_seconds),
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
    rules = evaluate(db, txn, customer, cfg=cfg)
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
    if action is not None:
        alert = Alert(
            customer_id=customer.id,
            alert_type="BEHAVIORAL_ANOMALY" if not any(r.rule_id in ("R005", "R006") for r in rules) else "SANCTIONS" if any(r.rule_id == "R006" for r in rules) else "PEP",
            risk_score=score,
            confidence=min(100.0, score * 1.0),
            triggered_rules={"rules": [r.rule_id for r in rules]},
            recommended_action=action,
            status="OPEN",
        )
        db.add(alert)

    db.flush()
    return rules, score, alert
