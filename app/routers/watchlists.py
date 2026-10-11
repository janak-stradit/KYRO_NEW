"""
routers/watchlists.py — sanctions watchlist source/run/entity visibility and
on-demand ingestion (Phase 4.1).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_permission
from app.models.watchlist import WatchlistEntity, WatchlistIngestionRun, WatchlistSource
from app.models.user import User
from app.schemas.common import Page
from app.schemas.watchlist import (
    IngestRequest,
    IngestResponse,
    WatchlistEntityOut,
    WatchlistIngestionRunOut,
    WatchlistSourceOut,
)
from app.services import screening_service
from app.services.watchlist_ingestion_service import ingest_all_enabled

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"], dependencies=[Depends(get_current_user)])


@router.get("/sources", response_model=list[WatchlistSourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[WatchlistSource]:
    return db.query(WatchlistSource).order_by(WatchlistSource.code).all()


@router.get("/screening-baseline")
def screening_baseline(
    limit: int = Query(500, ge=1, le=20000),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("watchlists.ingest", "rules.approve")),
) -> dict:
    """Dry run, nothing written: matches per customer with today's screening policy and without phonetic or identifier scoring."""
    return screening_service.screening_baseline(db, limit=limit)


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_ingest(
    data: IngestRequest,
    user: User = Depends(require_permission("watchlists.ingest")),
) -> IngestResponse:
    if data.run_async:
        from app.tasks.watchlist_tasks import ingest_watchlists_task

        task = ingest_watchlists_task.delay()
        return IngestResponse(status="QUEUED", task_id=task.id)

    from app.database import SessionLocal

    with SessionLocal() as db:
        runs = ingest_all_enabled(db)
        return IngestResponse(
            status="COMPLETED",
            result={
                "sources": len(runs),
                "results": [
                    {"source_id": str(r.source_id), "status": r.status, "records_added": r.records_added}
                    for r in runs
                ],
            },
        )


@router.get("/runs", response_model=Page[WatchlistIngestionRunOut])
def list_runs(
    pagination: PaginationParams = Depends(),
    source_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
) -> Page[WatchlistIngestionRunOut]:
    query = db.query(WatchlistIngestionRun)
    if source_id:
        query = query.filter(WatchlistIngestionRun.source_id == source_id)
    if status_filter:
        query = query.filter(WatchlistIngestionRun.status == status_filter)
    total = query.count()
    items = (
        query.order_by(WatchlistIngestionRun.started_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/entities", response_model=Page[WatchlistEntityOut])
def list_entities(
    pagination: PaginationParams = Depends(),
    source_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    q: str | None = None,
    is_active: bool = True,
    db: Session = Depends(get_db),
) -> Page[WatchlistEntityOut]:
    query = db.query(WatchlistEntity).filter(WatchlistEntity.is_active == is_active)
    if source_id:
        query = query.filter(WatchlistEntity.source_id == source_id)
    if entity_type:
        query = query.filter(WatchlistEntity.entity_type == entity_type)
    if q:
        query = query.filter(WatchlistEntity.primary_name.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(WatchlistEntity.primary_name).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)
