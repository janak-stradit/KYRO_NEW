"""
routers/regulatory.py — Regulatory knowledge base: sources, ingestion runs,
versioned section text and cited Q&A (Phase 11.3).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_role
from app.models.regulatory import RegulatoryIngestionRun, RegulatorySection, RegulatorySource
from app.models.user import User
from app.schemas.common import Page
from app.schemas.regulatory import (
    AskRequest,
    AskResponse,
    RegulatoryIngestionRunOut,
    RegulatorySectionOut,
    RegulatorySectionSummary,
    RegulatorySourceOut,
)
from app.services import regulatory_qa_service
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
