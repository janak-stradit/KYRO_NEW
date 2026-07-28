"""
tasks/etl_tasks.py — Background risk-scoring backstop.

The transactions API scores each transaction synchronously via the rules
engine on ingestion (see app.services.rules_engine). These Celery tasks are
the async safety net: they catch any transaction left unscored (e.g. loaded
through a future bulk/source-system import path that bypasses the API) and
run it through the same rules engine on a daily schedule.

ETL flow: Extract (find unscored transactions) -> Validate (drop orphans) ->
Transform & Load (score + persist via the rules engine).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.database import SessionLocal
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services.rules_engine import apply_to_transaction
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.etl_tasks.extract_from_source_system")
def extract_from_source_system(source: str | None = None, date_range: tuple[str, str] | None = None) -> list[str]:
    """Return IDs of transactions still pending risk scoring."""
    with SessionLocal() as db:
        query = db.query(Transaction.id).filter(Transaction.risk_flags.is_(None))
        if source:
            query = query.filter(Transaction.source_system == source)
        if date_range:
            start, end = (datetime.fromisoformat(d) for d in date_range)
            query = query.filter(Transaction.transaction_date >= start, Transaction.transaction_date <= end)
        return [str(row[0]) for row in query.all()]


@celery_app.task(name="app.tasks.etl_tasks.validate_transaction_data")
def validate_transaction_data(raw_data: list[str]) -> list[str]:
    """Drop transaction IDs whose transaction or owning customer no longer exists."""
    with SessionLocal() as db:
        valid: list[str] = []
        for tid in raw_data:
            txn = db.get(Transaction, uuid.UUID(tid))
            if txn is not None and db.get(Customer, txn.customer_id) is not None:
                valid.append(tid)
        return valid


@celery_app.task(name="app.tasks.etl_tasks.transform_and_load")
def transform_and_load(validated_data: list[str]) -> dict[str, int]:
    """Run the rules engine against each pending transaction and persist the result."""
    with SessionLocal() as db:
        scored = 0
        for tid in validated_data:
            txn = db.get(Transaction, uuid.UUID(tid))
            if txn is None or txn.risk_flags is not None:
                continue
            customer = db.get(Customer, txn.customer_id)
            if customer is None:
                continue
            apply_to_transaction(db, txn, customer)
            scored += 1
        db.commit()
        return {"scored": scored}


@celery_app.task(name="app.tasks.etl_tasks.run_daily_etl_pipeline")
def run_daily_etl_pipeline() -> dict[str, int]:
    pending_ids = extract_from_source_system(None, None)
    valid_ids = validate_transaction_data(pending_ids)
    return transform_and_load(valid_ids)
