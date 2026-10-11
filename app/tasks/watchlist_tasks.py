"""
tasks/watchlist_tasks.py — Celery entry points for the nightly watchlist
refresh: pull the enabled sanctions sources, then re-screen every active
customer against the refreshed data (perpetual/ongoing monitoring).
"""
from __future__ import annotations

from app.database import SessionLocal
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer
from app.services.screening_service import screen_beneficial_owner, screen_customer
from app.services.watchlist_ingestion_service import ingest_all_enabled
from app.tasks.celery_app import celery_app

_RESCREEN_BATCH_SIZE = 500


@celery_app.task(name="app.tasks.watchlist_tasks.ingest_watchlists_task")
def ingest_watchlists_task() -> dict:
    with SessionLocal() as db:
        runs = ingest_all_enabled(db)
        return {
            "sources": len(runs),
            "results": [
                {
                    "source_id": str(r.source_id),
                    "status": r.status,
                    "records_added": r.records_added,
                    "records_updated": r.records_updated,
                    "records_deactivated": r.records_deactivated,
                    "error_message": r.error_message,
                }
                for r in runs
            ],
        }


@celery_app.task(name="app.tasks.watchlist_tasks.rescreen_all_customers_task")
def rescreen_all_customers_task(batch_size: int = _RESCREEN_BATCH_SIZE) -> dict:
    """Offset-paginated rather than a streaming cursor, so each batch's
    commit doesn't invalidate an in-flight server-side cursor."""
    with SessionLocal() as db:
        screened = 0
        matches = 0
        offset = 0
        while True:
            batch = (
                db.query(Customer)
                .filter(Customer.kyc_status != "REJECTED")
                .order_by(Customer.id)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            for customer in batch:
                results = screen_customer(db, customer, triggered_by="SYSTEM")
                screened += 1
                matches += len(results)
            db.commit()
            offset += batch_size
        return {"screened": screened, "matches": matches}


@celery_app.task(name="app.tasks.watchlist_tasks.rescreen_all_beneficial_owners_task")
def rescreen_all_beneficial_owners_task(batch_size: int = _RESCREEN_BATCH_SIZE) -> dict:
    with SessionLocal() as db:
        screened = 0
        matches = 0
        offset = 0
        while True:
            batch = (
                db.query(BeneficialOwner)
                .filter(BeneficialOwner.effective_to.is_(None))
                .order_by(BeneficialOwner.id)
                .offset(offset)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            for owner in batch:
                results = screen_beneficial_owner(db, owner, triggered_by="SYSTEM")
                screened += 1
                matches += len(results)
            db.commit()
            offset += batch_size
        return {"screened": screened, "matches": matches}


@celery_app.task(name="app.tasks.watchlist_tasks.run_watchlist_refresh_pipeline")
def run_watchlist_refresh_pipeline() -> dict:
    ingest_result = ingest_watchlists_task()
    rescreen_customers_result = rescreen_all_customers_task()
    rescreen_owners_result = rescreen_all_beneficial_owners_task()
    return {
        "ingest": ingest_result,
        "rescreen_customers": rescreen_customers_result,
        "rescreen_beneficial_owners": rescreen_owners_result,
    }
