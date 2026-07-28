"""
tasks/celery_app.py — Celery application, Redis-backed broker/result store.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kyro_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.etl_tasks", "app.tasks.ml_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

celery_app.conf.beat_schedule = {
    "run-daily-etl-pipeline": {
        "task": "app.tasks.etl_tasks.run_daily_etl_pipeline",
        "schedule": crontab(hour=2, minute=0),
    },
    "check-ml-retraining-weekly": {
        "task": "app.tasks.ml_tasks.check_retraining_task",
        "schedule": crontab(day_of_week=0, hour=3, minute=0),
    },
}
