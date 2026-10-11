"""
services/watchlist_ingestion_service.py — fetches each enabled watchlist
source, upserts its records into WatchlistEntity, deactivates entities no
longer present in the latest pull, and records an auditable
WatchlistIngestionRun for every attempt (Phase 4.1).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.watchlist import WatchlistEntity, WatchlistIngestionRun, WatchlistSource
from app.services.screening_service import normalize_name, search_columns
from app.services.watchlist_adapters import ADAPTERS

settings = get_settings()


def _fetch(url: str) -> bytes:
    with httpx.Client(timeout=settings.watchlist_http_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _entity_values(source_id, record, run_id: str, now: datetime) -> dict:
    return {
        "source_id": source_id,
        "external_id": record.external_id,
        "entity_type": record.entity_type,
        "primary_name": record.primary_name,
        "normalized_name": normalize_name(record.primary_name),
        "aka_names": record.aka_names,
        "date_of_birth": record.date_of_birth,
        "place_of_birth": record.place_of_birth,
        "nationalities": record.nationalities,
        "addresses": record.addresses,
        "programs": record.programs,
        "remarks": record.remarks,
        "raw_data": record.raw_data,
        "is_active": True,
        "list_version": run_id,
        "last_seen_at": now,
        **search_columns(record.primary_name, record.aka_names),
    }


def ingest_source(db: Session, source: WatchlistSource) -> WatchlistIngestionRun:
    """Fetch + parse + upsert one source. Always persists a run row, even on
    failure, so ingestion history is a complete audit trail."""
    now = datetime.now(timezone.utc)
    run = WatchlistIngestionRun(source_id=source.id, status="PENDING", started_at=now)
    db.add(run)
    source.last_fetched_at = now
    db.commit()  # persist the PENDING run durably before risky work, so a
    # later rollback (on failure) can't undo the run row itself — only the
    # partial upserts from this attempt.
    db.refresh(run)
    run_id = str(run.id)

    try:
        adapter = ADAPTERS[source.code]
        raw_bytes = _fetch(source.url)
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        run.file_hash = file_hash

        if file_hash == source.last_file_hash:
            run.status = "SKIPPED_UNCHANGED"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return run

        existing_ids = {
            row[0]
            for row in db.query(WatchlistEntity.external_id).filter(WatchlistEntity.source_id == source.id).all()
        }

        seen_external_ids: set[str] = set()
        added = updated = 0

        for record in adapter(raw_bytes):
            if record.external_id in seen_external_ids:
                continue  # adapter should already dedupe, but never upsert the same key twice per run
            seen_external_ids.add(record.external_id)
            values = _entity_values(source.id, record, run_id, now)

            stmt = pg_insert(WatchlistEntity).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source_id", "external_id"],
                set_={k: v for k, v in values.items() if k not in ("source_id", "external_id")},
            )
            db.execute(stmt)

            if record.external_id in existing_ids:
                updated += 1
            else:
                added += 1

        if not seen_external_ids:
            raise ValueError(f"{source.code}: adapter produced zero records; refusing to deactivate the source")

        deactivated = (
            db.query(WatchlistEntity)
            .filter(
                WatchlistEntity.source_id == source.id,
                WatchlistEntity.is_active.is_(True),
                ~WatchlistEntity.external_id.in_(seen_external_ids),
            )
            .update({"is_active": False}, synchronize_session=False)
        )

        run.status = "SUCCESS"
        run.records_seen = len(seen_external_ids)
        run.records_added = added
        run.records_updated = updated
        run.records_deactivated = deactivated
        run.completed_at = datetime.now(timezone.utc)
        source.last_success_at = run.completed_at
        source.last_file_hash = file_hash
        db.commit()
    except Exception as exc:  # noqa: BLE001 — one source's failure must not block the others
        db.rollback()  # discards this attempt's partial upserts; the PENDING
        # run row itself survives since it was committed before this block
        run.status = "FAILED"
        run.error_message = str(exc)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

    return run


def ingest_all_enabled(db: Session) -> list[WatchlistIngestionRun]:
    sources = db.query(WatchlistSource).filter(WatchlistSource.is_enabled.is_(True)).all()
    return [ingest_source(db, source) for source in sources]
