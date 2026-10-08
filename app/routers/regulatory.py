"""
routers/regulatory.py — Regulatory knowledge base: sources, ingestion runs,
versioned section text and cited Q&A (Phase 11.3).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import AIDisabledError, AIGateway, AIProviderError
from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_role
from app.models.obligation import Obligation
from app.models.regulatory import RegulatoryIngestionRun, RegulatorySection, RegulatorySource
from app.models.user import User
from app.schemas.common import Page
from app.schemas.regulatory import (
    AskRequest,
    AskResponse,
    ObligationExtractResult,
    ObligationOut,
    ObligationReview,
    ObligationSummary,
    RegulatoryIngestionRunOut,
    RegulatorySectionOut,
    RegulatorySectionSummary,
    RegulatorySourceOut,
)
from app.services import obligation_service, regulatory_qa_service
from app.services.regulatory_ingestion_service import ingest_all_enabled, ingest_source

router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory"], dependencies=[Depends(get_current_user)])


@router.get("/sources", response_model=list[RegulatorySourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[RegulatorySource]:
    return db.query(RegulatorySource).order_by(RegulatorySource.code).all()


@router.post("/ingest", response_model=list[RegulatoryIngestionRunOut])
def trigger_ingest(
    source_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> list[RegulatoryIngestionRun]:
    """Pull one source, or every enabled source, now. Runs are also scheduled daily."""
    if source_id is None:
        return ingest_all_enabled(db)
    source = db.get(RegulatorySource, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regulatory source not found")
    return [ingest_source(db, source)]


@router.get("/runs", response_model=Page[RegulatoryIngestionRunOut])
def list_runs(
    pagination: PaginationParams = Depends(),
    source_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
) -> Page[RegulatoryIngestionRunOut]:
    query = db.query(RegulatoryIngestionRun)
    if source_id:
        query = query.filter(RegulatoryIngestionRun.source_id == source_id)
    total = query.count()
    items = (
        query.order_by(RegulatoryIngestionRun.started_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/sections", response_model=Page[RegulatorySectionSummary])
def list_sections(
    pagination: PaginationParams = Depends(),
    source_id: uuid.UUID | None = None,
    section_ref: str | None = None,
    include_superseded: bool = False,
    db: Session = Depends(get_db),
) -> Page[RegulatorySectionSummary]:
    """Current sections; pass section_ref with include_superseded=true for a section's version history."""
    query = db.query(RegulatorySection)
    if source_id:
        query = query.filter(RegulatorySection.source_id == source_id)
    if section_ref:
        query = query.filter(RegulatorySection.section_ref == section_ref)
    if not include_superseded:
        query = query.filter(RegulatorySection.is_current.is_(True))
    total = query.count()
    items = (
        query.order_by(RegulatorySection.section_ref, RegulatorySection.first_seen_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/sections/{section_id}", response_model=RegulatorySectionOut)
def get_section(section_id: uuid.UUID, db: Session = Depends(get_db)) -> RegulatorySection:
    section = db.get(RegulatorySection, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
    return section


@router.post("/ask", response_model=AskResponse)
def ask(data: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Answer a regulatory question from loaded sources only, with citations."""
    return regulatory_qa_service.ask(db, data.question, requested_by=user.id)


# ── Obligations register ─────────────────────────────────────────────────

@router.post("/obligations/extract", response_model=ObligationExtractResult)
def extract_obligations(
    source_id: uuid.UUID | None = None,
    section_id: uuid.UUID | None = None,
    redo: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> dict:
    """
    Have the AI propose obligations for one section, or for every current
    section of a source (sections that already have obligations are skipped
    unless redo=true). Proposals wait for review; nothing is confirmed here.
    """
    if (source_id is None) == (section_id is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give exactly one of source_id or section_id")
    provider = AIGateway(db).status()["provider"]
    try:
        if section_id is not None:
            section = db.get(RegulatorySection, section_id)
            if section is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Section not found")
            created = obligation_service.extract_for_section(db, section, requested_by=user.id)
            result = {"sections_processed": 1, "sections_skipped": 0, "obligations_proposed": len(created)}
        else:
            if db.get(RegulatorySource, source_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Regulatory source not found")
            result = obligation_service.extract_for_source(db, source_id, requested_by=user.id, only_missing=not redo)
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return {**result, "extracted_by": provider}


@router.get("/obligations/summary", response_model=ObligationSummary)
def obligations_summary(db: Session = Depends(get_db)) -> dict:
    def counts(column) -> dict[str, int]:
        return dict(db.query(column, func.count()).group_by(column).all())

    return {
        "by_status": counts(Obligation.status),
        "by_category": counts(Obligation.category),
        "unverified_quotes": db.query(Obligation)
        .filter(Obligation.quote_verified.is_(False), Obligation.status.in_(("PROPOSED", "CONFIRMED")))
        .count(),
    }


@router.get("/obligations", response_model=Page[ObligationOut])
def list_obligations(
    pagination: PaginationParams = Depends(),
    status_filter: str | None = None,
    category: str | None = None,
    section_ref: str | None = None,
    source_id: uuid.UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> Page[ObligationOut]:
    query = db.query(Obligation)
    if status_filter:
        query = query.filter(Obligation.status == status_filter)
    if category:
        query = query.filter(Obligation.category == category)
    if section_ref:
        query = query.filter(Obligation.section_ref == section_ref)
    if source_id:
        query = query.join(RegulatorySection, RegulatorySection.id == Obligation.section_id).filter(
            RegulatorySection.source_id == source_id
        )
    if q:
        like = f"%{q}%"
        query = query.filter(
            Obligation.action.ilike(like) | Obligation.obligated_party.ilike(like) | Obligation.section_ref.ilike(like)
        )
    total = query.count()
    items = (
        query.order_by(Obligation.section_ref, Obligation.created_at, Obligation.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.put("/obligations/{obligation_id}/review", response_model=ObligationOut)
def review_obligation(
    obligation_id: uuid.UUID,
    data: ObligationReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> Obligation:
    obligation = db.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Obligation not found")
    if obligation.status == "SUPERSEDED":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The section text has changed; extract obligations for the new version"
        )
    edits = data.model_dump(exclude={"decision", "notes"}, exclude_none=True)
    return obligation_service.review(
        db, obligation, decision=data.decision, reviewer_id=user.id, edits=edits, notes=data.notes
    )
