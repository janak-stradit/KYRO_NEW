"""
services/retraining_service.py — Decides whether accumulated analyst
feedback warrants a retrain. A triggered retrain always deploys as a
traffic-split candidate rather than overwriting the active model outright,
so a regression can't silently reach 100% of traffic.
"""
from __future__ import annotations

from app.config import get_settings
from app.database import SessionLocal
from app.ml.training.pipeline import run_training_pipeline
from app.services import feedback_service
from app.services.alert_service import ML_VERSION

CANDIDATE_TRAFFIC_PCT = 10.0


def retrain_if_needed(ml_version: str | None = ML_VERSION) -> dict:
    settings = get_settings()
    db = SessionLocal()
    try:
        feedback = feedback_service.collect_feedback(db, days=30, ml_version=ml_version)
    finally:
        db.close()

    if len(feedback) < settings.retrain_threshold:
        return {"status": "INSUFFICIENT_DATA", "needed": settings.retrain_threshold, "have": len(feedback)}

    performance = feedback_service.evaluate_performance(feedback)
    if performance["precision"] is not None and performance["precision"] < settings.performance_threshold:
        result = run_training_pipeline(as_candidate=True, candidate_traffic_pct=CANDIDATE_TRAFFIC_PCT)
        return {
            "status": "RETRAINING_TRIGGERED",
            "old_precision": performance["precision"],
            "new_versions": result["versions"],
            "new_metrics": result["metrics"],
        }
    return {"status": "PERFORMANCE_OK", "precision": performance["precision"]}
