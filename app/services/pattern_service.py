"""
services/pattern_service.py — Behavioural pattern activity, counted from the
rules that actually fired on alerts.

Each pattern groups one or more rules (R001–R010). An alert counts towards a
pattern when any of that pattern's rules is in its `triggered_rules`, so one
alert can count towards several patterns. Inactive reactivation has no rule;
it is derived from transaction history.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.alert import Alert

PATTERNS: list[dict[str, Any]] = [
    {
        "id": "THRESHOLD_BREACH", "legacy_name": "TRANSACTION_SIZE", "label": "Threshold Breach",
        "description": "Transactions above the reporting threshold, or in suspiciously round amounts.",
        "icon": "fa-money-bill-wave", "color": "danger", "rule_ids": ["R001", "R009"], "severity": "HIGH",
    },
    {
        "id": "VELOCITY_SPIKE", "legacy_name": "FREQUENCY", "label": "Velocity Spike",
        "description": "More transactions in a day or an hour than the configured limit.",
        "icon": "fa-tachometer-alt", "color": "warning", "rule_ids": ["R002", "R003"], "severity": "MEDIUM",
    },
    {
        "id": "GEOGRAPHIC_SHIFT", "legacy_name": "GEOGRAPHY", "label": "Geographic Shift",
        "description": "Counterparties in sanctioned or high-risk jurisdictions.",
        "icon": "fa-globe", "color": "info", "rule_ids": ["R004"], "severity": "HIGH",
    },
    {
        "id": "COUNTERPARTY_CHANGES", "legacy_name": "COUNTERPARTY", "label": "Counterparty Changes",
        "description": "First transaction with a counterparty the customer has not dealt with before.",
        "icon": "fa-network-wired", "color": "primary", "rule_ids": ["R007"], "severity": "MEDIUM",
    },
    {
        "id": "COMPLEXITY_SHIFT", "legacy_name": "COMPLEXITY_SHIFT", "label": "Complexity Shift",
        "description": "Weekend activity or several transactions within a minute, which can indicate layering.",
        "icon": "fa-project-diagram", "color": "secondary", "rule_ids": ["R008", "R010"], "severity": "MEDIUM",
    },
    {
        "id": "INACTIVE_REACTIVATION", "legacy_name": "INACTIVE_REACTIVATION", "label": "Inactive Reactivation",
        "description": "Customers active in the last 30 days after no activity in the 60 days before that.",
        "icon": "fa-redo", "color": "success", "rule_ids": [], "severity": "HIGH",
    },
]
_PATTERN_OF_RULE = {rule: p["id"] for p in PATTERNS for rule in p["rule_ids"]}
PATTERN_LABELS = {p["id"]: p["label"] for p in PATTERNS}


def _rules_of(triggered_rules: Any) -> set[str]:
    rules = triggered_rules.get("rules") if isinstance(triggered_rules, dict) else triggered_rules
    return {str(r) for r in rules} if isinstance(rules, list) else set()


def _reactivated_customers(db: Session) -> int:
    return db.execute(
        text(
            """
            SELECT COUNT(DISTINCT t.customer_id) FROM app.transactions t
            WHERE t.transaction_date >= NOW() - INTERVAL '30 days'
              AND t.customer_id NOT IN (
                  SELECT DISTINCT customer_id FROM app.transactions
                  WHERE transaction_date >= NOW() - INTERVAL '90 days'
                    AND transaction_date < NOW() - INTERVAL '30 days'
              )
            """
        )
    ).scalar() or 0


def pattern_activity(db: Session, *, days: int = 30) -> dict[str, Any]:
    """Per-pattern and per-(customer, pattern) activity for alerts created in the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = (
        db.query(Alert.customer_id, Alert.triggered_rules, Alert.risk_score, Alert.status, Alert.created_at)
        .filter(Alert.created_at >= cutoff)
        .all()
    )

    stats = {p["id"]: {"alerts": 0, "open_alerts": 0, "customers": set()} for p in PATTERNS}
    by_customer: dict[tuple, dict[str, Any]] = {}
    matched_alerts = 0
    matched_customers: set = set()

    for customer_id, triggered_rules, risk_score, status, created_at in alerts:
        patterns = {_PATTERN_OF_RULE[r] for r in _rules_of(triggered_rules) if r in _PATTERN_OF_RULE}
        if not patterns:
            continue
        matched_alerts += 1
        matched_customers.add(customer_id)
        is_open = status != "RESOLVED"
        for pattern in patterns:
            s = stats[pattern]
            s["alerts"] += 1
            s["open_alerts"] += is_open
            s["customers"].add(customer_id)
            row = by_customer.setdefault(
                (customer_id, pattern),
                {"customer_id": customer_id, "pattern": pattern, "alerts": 0, "open_alerts": 0,
                 "max_risk_score": 0, "last_triggered_at": created_at},
            )
            row["alerts"] += 1
            row["open_alerts"] += is_open
            row["max_risk_score"] = max(row["max_risk_score"], risk_score or 0)
            row["last_triggered_at"] = max(row["last_triggered_at"], created_at)

    reactivated = _reactivated_customers(db)
    patterns_out = []
    for p in PATTERNS:
        s = stats[p["id"]]
        derived = not p["rule_ids"]
        patterns_out.append({
            **p,
            "hit_count": reactivated if derived else s["alerts"],
            "customers": reactivated if derived else len(s["customers"]),
            "open_alerts": None if derived else s["open_alerts"],
        })

    return {
        "window_days": days,
        "matched_alerts": matched_alerts,
        "matched_customers": len(matched_customers),
        "patterns": patterns_out,
        "customer_rows": list(by_customer.values()),
    }
