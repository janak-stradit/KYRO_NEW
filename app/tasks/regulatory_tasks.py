"""
tasks/regulatory_tasks.py — Celery entry point for the daily regulatory
refresh: pull every enabled source and store any changed sections as new
versions (Phase 11.3).
"""
from __future__ import annotations

from app.database import SessionLocal
from app.services.regulatory_ingestion_service import ingest_all_enabled
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.regulatory_tasks.ingest_regulatory_sources_task")
def ingest_regulatory_sources_task() -> dict:
    with SessionLocal() as db:
        runs = ingest_all_enabled(db)
        return {
            "sources": len(runs),
            "results": [
                {
                    "source_id": str(r.source_id),
                    "status": r.status,
                    "as_of": r.as_of,
                    "sections_added": r.sections_added,
                    "sections_changed": r.sections_changed,
                    "sections_removed": r.sections_removed,
                    "error_message": r.error_message,
                }
                for r in runs
            ],
        }


@celery_app.task(name="app.tasks.regulatory_tasks.activate_due_rule_changes_task")
def activate_due_rule_changes_task() -> dict:
    """Apply approved rule changes whose effective date has arrived."""
    from app.services import change_service

    with SessionLocal() as db:
        return {"activated": change_service.activate_due(db)}


@celery_app.task(name="app.tasks.regulatory_tasks.sync_federal_register_task")
def sync_federal_register_task() -> dict:
    """Fetch new rules and proposed rules for the loaded CFR parts."""
    from app.services import federal_register_service

    with SessionLocal() as db:
        return federal_register_service.sync(db)
