"""
tasks/fx_tasks.py — Daily exchange-rate load (ECB reference rates, published
around 16:00 CET on working days) and the base-amount backfill that follows it.
"""
from __future__ import annotations

from app.database import SessionLocal
from app.services import fx_service
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.fx_tasks.refresh_fx_rates_task")
def refresh_fx_rates_task() -> dict:
    with SessionLocal() as db:
        result = fx_service.refresh_from_ecb(db)
        result["backfilled"] = fx_service.backfill_amount_base(db)
        return {**result, "rate_date": result["rate_date"].isoformat() if result["rate_date"] else None}


@celery_app.task(name="app.tasks.fx_tasks.backfill_amount_base_task")
def backfill_amount_base_task() -> dict:
    with SessionLocal() as db:
        return {"backfilled": fx_service.backfill_amount_base(db)}
