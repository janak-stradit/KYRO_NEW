"""
tasks/ml_tasks.py — Celery entry point for (re)training the ML models.
Training can take a while, so it's dispatched async rather than run inline
on the request that triggers it (see routers/ml.py's /train endpoint).
"""
from __future__ import annotations

from app.ml.training.pipeline import run_training_pipeline
from app.services.retraining_service import retrain_if_needed
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.ml_tasks.run_training_pipeline_task")
def run_training_pipeline_task(
    as_candidate: bool = False, candidate_traffic_pct: float = 10.0, limit: int | None = None
) -> dict:
    return run_training_pipeline(as_candidate=as_candidate, candidate_traffic_pct=candidate_traffic_pct, limit=limit)


@celery_app.task(name="app.tasks.ml_tasks.check_retraining_task")
def check_retraining_task() -> dict:
    return retrain_if_needed()
