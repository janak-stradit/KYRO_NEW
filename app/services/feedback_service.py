"""
services/feedback_service.py — Collects analyst resolutions on ML-generated
alerts and evaluates precision/false-positive rate to inform retraining.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy.orm import Session

from app.models.alert import Alert


def collect_feedback(db: Session, *, days: int = 30, ml_version: str | None = None) -> list[Alert]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(Alert).filter(
        Alert.status == "RESOLVED",
        Alert.resolved_at >= cutoff,
        Alert.is_false_positive.isnot(None),
    )
    if ml_version:
        query = query.filter(Alert.ml_version == ml_version)
    return query.all()


def _rules_of(alert: Alert) -> list[str]:
    rules = alert.triggered_rules
    if isinstance(rules, dict):
        rules = rules.get("rules") or []
    return sorted({str(r) for r in rules}) if isinstance(rules, list) else []


def _summarise(alerts: list[Alert]) -> dict:
    resolved = [a for a in alerts if a.status == "RESOLVED" and a.is_false_positive is not None]
    false_positives = sum(1 for a in resolved if a.is_false_positive)
    hours = [(a.resolved_at - a.created_at).total_seconds() / 3600 for a in resolved if a.resolved_at]
    return {
        "alerts": len(alerts),
        "resolved": len(resolved),
        "false_positives": false_positives,
        "false_positive_rate": false_positives / len(resolved) if resolved else None,
        "sar_filed": sum(1 for a in alerts if a.resolution_outcome == "SAR_FILED"),
        "escalated": sum(1 for a in alerts if a.resolution_outcome == "ESCALATED"),
        "median_hours_to_disposition": round(median(hours), 2) if hours else None,
        "reasons": dict(Counter(r for a in alerts for r in (a.resolution_reasons or [])).most_common()),
    }


def disposition_baseline(db: Session, *, days: int = 90) -> dict:
    """
    False-positive rate, volumes and time-to-disposition for alerts created in
    the window, overall and per rule / rule combination (plan 11.2 step 1).
    Rates are None until at least one alert in the group has been resolved.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    alerts = db.query(Alert).filter(Alert.created_at >= cutoff).all()

    by_rule: dict[str, list[Alert]] = defaultdict(list)
    by_combination: dict[str, list[Alert]] = defaultdict(list)
    for alert in alerts:
        rules = _rules_of(alert)
        by_combination["+".join(rules) or "NO_RULE"].append(alert)
        for rule in rules or ["NO_RULE"]:
            by_rule[rule].append(alert)

    def rows(groups: dict[str, list[Alert]], key: str) -> list[dict]:
        return sorted(
            ({key: name, **_summarise(group)} for name, group in groups.items()),
            key=lambda row: (-row["alerts"], row[key]),
        )

    return {
        "window_days": days,
        "overall": _summarise(alerts),
        "by_rule": rows(by_rule, "rule"),
        "by_rule_combination": rows(by_combination, "rules"),
    }


def evaluate_performance(feedback: list[Alert]) -> dict:
    total = len(feedback)
    if total == 0:
        return {"precision": None, "false_positive_rate": None, "total_reviewed": 0}

    false_positives = sum(1 for a in feedback if a.is_false_positive)
    true_positives = total - false_positives
    return {
        "precision": true_positives / total,
        "false_positive_rate": false_positives / total,
        "total_reviewed": total,
    }
