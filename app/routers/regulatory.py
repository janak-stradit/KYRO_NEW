"""
routers/regulatory.py — Regulatory knowledge base: sources, ingestion runs,
versioned section text and cited Q&A (Phase 11.3).
"""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai import AIDisabledError, AIGateway, AIProviderError
from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_permission
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.regulatory import RegulatoryIngestionRun, RegulatorySection, RegulatorySource
from app.models.user import User
from app.schemas.common import Page
from app.schemas.regulatory import (
    AskRequest,
    AskResponse,
    ControlOut,
    MappingCreate,
    MappingOut,
    MappingReview,
    ObligationExtractResult,
    ObligationOut,
    ObligationReview,
    ObligationSummary,
    RegulatoryIngestionRunOut,
    RegulatorySectionOut,
    RegulatorySectionSummary,
    RegulatorySourceOut,
)
from app.services import mapping_service, obligation_service, regulatory_qa_service
from app.services.control_catalogue import CONTROLS, CONTROLS_BY_CODE
from app.services.regulatory_ingestion_service import ingest_all_enabled, ingest_source

router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory"], dependencies=[Depends(get_current_user)])


@router.get("/sources", response_model=list[RegulatorySourceOut])
def list_sources(db: Session = Depends(get_db)) -> list[RegulatorySource]:
    return db.query(RegulatorySource).order_by(RegulatorySource.code).all()


@router.post("/ingest", response_model=list[RegulatoryIngestionRunOut])
def trigger_ingest(
    source_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("regulatory.ingest")),
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
    user: User = Depends(require_permission("obligations.manage")),
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
    user: User = Depends(require_permission("obligations.manage")),
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


# ── Obligation → control mapping and traceability (Phase 11.4) ───────────

@router.get("/controls", response_model=list[ControlOut])
def list_controls() -> list[dict]:
    """The KYRO controls obligations can be mapped to."""
    return [
        {"code": c.code, "kind": c.kind, "name": c.name, "description": c.description, "config_keys": list(c.config_keys)}
        for c in CONTROLS
    ]


@router.post("/mappings/propose")
def propose_mappings(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("mappings.manage")),
) -> dict:
    """Have the AI propose controls for every confirmed obligation that has no mapping yet."""
    provider = AIGateway(db).status()["provider"]
    try:
        result = mapping_service.propose_for_unmapped(db, requested_by=user.id)
    except AIDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except AIProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return {**result, "proposed_by": provider}


@router.post("/mappings", response_model=MappingOut, status_code=status.HTTP_201_CREATED)
def add_mapping(
    data: MappingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("mappings.manage")),
) -> ObligationMapping:
    """Map a control to an obligation by hand; it is confirmed immediately."""
    obligation = db.get(Obligation, data.obligation_id)
    if obligation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Obligation not found")
    if obligation.status != "CONFIRMED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only confirmed obligations can be mapped")
    if data.control_code not in CONTROLS_BY_CODE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown control: {data.control_code}")
    return mapping_service.add_manual(
        db, obligation, control_code=data.control_code, rationale=data.rationale, user_id=user.id
    )


@router.put("/mappings/{mapping_id}/review", response_model=MappingOut)
def review_mapping(
    mapping_id: uuid.UUID,
    data: MappingReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("mappings.manage")),
) -> ObligationMapping:
    mapping = db.get(ObligationMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mapping not found")
    return mapping_service.review(db, mapping, decision=data.decision, reviewer_id=user.id)


_TRACE_COLUMNS = [
    "section_ref", "section_version", "obligated_party", "action", "deadline", "category",
    "mapping_status", "control_code", "control_name", "rule_config", "alerts", "false_positive_rate", "rationale",
]


@router.get("/traceability")
def traceability(
    days: int = Query(90, ge=1, le=730),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
):
    """Regulation version → obligation → control → rule config → alerts. `format=csv` for audits."""
    data = mapping_service.traceability(db, days=days)
    if format == "json":
        return data
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_TRACE_COLUMNS)
    for row in data["rows"]:
        values = {**row, "rule_config": "; ".join(f"{k}={v}" for k, v in row["rule_config"].items())}
        writer.writerow(["" if values[c] is None else values[c] for c in _TRACE_COLUMNS])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kyro-traceability-matrix.csv"},
    )
