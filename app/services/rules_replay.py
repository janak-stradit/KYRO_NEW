"""
services/rules_replay.py — Re-runs the rules engine over a past period with the
current switches and with proposed ones, and reports the difference. Nothing is
written: every evaluation runs inside a savepoint that is rolled back.

Its main use is the "no silent loss" check before a rules change goes live:
a case that was escalated, became a SAR or was a true positive, but whose
customer would no longer alert around the time it was raised, is listed as a
possible lost true positive for Compliance to look at.

Alerts do not record their transactions before rules engine R1, so the link is
made by customer and time (a transaction within a day of the alert).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services import fx_service
from app.services.rules_engine import WEAK_RULES, RuleOptions, evaluate, recommended_action_for, resolve_config, score_from_rules

PRODUCTIVE = ("SAR_FILED", "ESCALATED", "TRUE_POSITIVE_NO_SAR")
MAX_TRANSACTIONS = 20_000


def _would_alert(db: Session, txn: Transaction, customer: Customer, cfg: dict, options: RuleOptions) -> tuple[bool, list[str]]:
    if options.base_currency and txn.amount_base is None:
        fx_service.apply(db, txn)  # rolled back with the savepoint
    rules = evaluate(db, txn, customer, cfg=cfg, options=options)
    score = score_from_rules(rules, severity_weights=cfg["SEVERITY_WEIGHT"])
    action = recommended_action_for(rules, score, alert_threshold=cfg["ALERT_THRESHOLD"], edd_threshold=cfg["EDD_THRESHOLD"])
    if options.noise_reduction and not any(r.rule_id not in WEAK_RULES for r in rules):
        action = None
    return action is not None, [r.rule_id for r in rules]


def replay(db: Session, start: datetime, end: datetime, proposed: RuleOptions, *, limit: int = MAX_TRANSACTIONS) -> dict:
    current = RuleOptions.from_settings()
    txns = (
        db.query(Transaction).filter(Transaction.transaction_date >= start, Transaction.transaction_date < end)
        .order_by(Transaction.transaction_date).limit(limit).all()
    )
    customers: dict = {}
    configs: dict = {}
    rule_hits = {"current": Counter(), "proposed": Counter()}
    alerting = {"current": [], "proposed": []}  # (customer_id, transaction_date)

    savepoint = db.begin_nested()
    try:
        for txn in txns:
            customer = customers.get(txn.customer_id) or customers.setdefault(txn.customer_id, db.get(Customer, txn.customer_id))
            if customer is None:
                continue
            cfg = configs.get(customer.id) or configs.setdefault(customer.id, resolve_config(db, customer))
            for label, options in (("current", current), ("proposed", proposed)):
                alerts, rules = _would_alert(db, txn, customer, cfg, options)
                rule_hits[label].update(rules)
                if alerts:
                    alerting[label].append((txn.customer_id, txn.transaction_date))
    finally:
        savepoint.rollback()

    def alerted_near(label: str, customer_id, at: datetime) -> bool:
        return any(c == customer_id and abs(t - at) <= timedelta(days=1) for c, t in alerting[label])

    productive = (
        db.query(Alert).filter(Alert.created_at >= start, Alert.created_at < end + timedelta(days=1))
        .filter((Alert.resolution_outcome.in_(PRODUCTIVE)) | (Alert.status == "ESCALATED")).all()
    )
    lost = [
        {"alert_id": str(a.id), "customer_id": str(a.customer_id), "outcome": a.resolution_outcome or a.status,
         "created_at": a.created_at.isoformat()}
        for a in productive
        if alerted_near("current", a.customer_id, a.created_at) and not alerted_near("proposed", a.customer_id, a.created_at)
    ]
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "transactions_replayed": len(txns),
        "truncated": len(txns) >= limit,
        "current_options": asdict(current),
        "proposed_options": asdict(proposed),
        "alerting_transactions": {k: len(v) for k, v in alerting.items()},
        "customers_alerting": {k: len({c for c, _ in v}) for k, v in alerting.items()},
        "rule_hits": {k: dict(sorted(v.items())) for k, v in rule_hits.items()},
        "productive_cases_in_period": len(productive),
        "possible_lost_true_positives": lost,
    }
