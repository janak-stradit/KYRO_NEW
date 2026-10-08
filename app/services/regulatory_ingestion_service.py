"""
services/regulatory_ingestion_service.py — pulls each enabled regulatory
source, stores new or changed sections as new versions, makes the current
text searchable, and records a RegulatoryIngestionRun for every attempt
(Phase 11.3; same shape as watchlist ingestion).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.ai.retrieval import index_text
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.obligation import Obligation
from app.models.regulatory import RegulatoryIngestionRun, RegulatorySection, RegulatorySource
from app.services import ecfr_adapter
from app.services.ecfr_adapter import SectionRecord

# source_kind -> fetch(config) returning (as_of_date, sections)
ADAPTERS: dict[str, Callable[[dict[str, Any]], tuple[str, list[SectionRecord]]]] = {
    "ECFR": lambda config: ecfr_adapter.fetch(config),
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _supersede_obligations(db: Session, section: RegulatorySection) -> None:
    """Obligations drawn from text that has changed or gone need a fresh look."""
    db.query(Obligation).filter(
        Obligation.section_id == section.id, Obligation.status.in_(("PROPOSED", "CONFIRMED"))
    ).update({Obligation.status: "SUPERSEDED"}, synchronize_session=False)


def ingest_source(db: Session, source: RegulatorySource) -> RegulatoryIngestionRun:
    """Fetch + compare + store one source. Always persists a run row, even on
    failure, so ingestion history is a complete audit trail."""
    now = datetime.now(timezone.utc)
    run = RegulatoryIngestionRun(source_id=source.id, status="PENDING", started_at=now)
    db.add(run)
    source.last_fetched_at = now
    db.commit()  # the run row must survive a rollback of this attempt's changes
    db.refresh(run)

    try:
        as_of, records = ADAPTERS[source.source_kind](source.config)
        if not records:
            raise ValueError(f"{source.code}: source returned no sections; keeping the existing text")

        hashes = {r.section_ref: _hash(f"{r.heading}\n{r.content}") for r in records}
        run.as_of = as_of
        run.content_hash = _hash("".join(f"{ref}:{h};" for ref, h in sorted(hashes.items())))
        run.sections_seen = len(records)

        if run.content_hash == source.last_content_hash:
            run.status = "SKIPPED_UNCHANGED"
            run.completed_at = datetime.now(timezone.utc)
            source.last_success_at = run.completed_at
            db.commit()
            return run

        current = {
            s.section_ref: s
            for s in db.query(RegulatorySection).filter(
                RegulatorySection.source_id == source.id, RegulatorySection.is_current.is_(True)
            )
        }

        for record in records:
            existing = current.get(record.section_ref)
            if existing is not None and existing.content_hash == hashes[record.section_ref]:
                continue
            if existing is not None:
                existing.is_current = False
                existing.superseded_at = now
                _supersede_obligations(db, existing)
                run.sections_changed += 1
            else:
                run.sections_added += 1

            db.add(
                RegulatorySection(
                    source_id=source.id,
                    run_id=run.id,
                    section_ref=record.section_ref,
                    heading=record.heading[:500],
                    content=record.content,
                    content_hash=hashes[record.section_ref],
                    version=record.version,
                    url=record.url,
                    source_note=record.source_note,
                )
            )
            index_text(
                db,
                source_type="REGULATION",
                source_ref=record.section_ref,
                version=record.version,
                title=record.heading[:500],
                citation=record.section_ref,
                text=record.content,
                meta={"url": record.url, "source_code": source.code},
            )

        for ref in set(current) - set(hashes):
            current[ref].is_current = False
            current[ref].superseded_at = now
            _supersede_obligations(db, current[ref])
            db.query(KnowledgeChunk).filter(
                KnowledgeChunk.source_type == "REGULATION", KnowledgeChunk.source_ref == ref
            ).update({KnowledgeChunk.is_current: False}, synchronize_session=False)
            run.sections_removed += 1

        run.status = "SUCCESS"
        run.completed_at = datetime.now(timezone.utc)
        source.last_success_at = run.completed_at
        source.last_content_hash = run.content_hash
        db.commit()
    except Exception as exc:  # noqa: BLE001 — one source's failure must not block the others
        db.rollback()
        run.status = "FAILED"
        run.error_message = str(exc)[:2000]
        run.sections_added = run.sections_changed = run.sections_removed = 0
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

    return run


def ingest_all_enabled(db: Session) -> list[RegulatoryIngestionRun]:
    sources = db.query(RegulatorySource).filter(RegulatorySource.is_enabled.is_(True)).order_by(RegulatorySource.code)
    return [ingest_source(db, source) for source in sources.all()]
