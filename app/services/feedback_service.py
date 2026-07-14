"""
services/feedback_service.py — Collects analyst resolutions on ML-generated
alerts and evaluates precision/false-positive rate to inform retraining.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
