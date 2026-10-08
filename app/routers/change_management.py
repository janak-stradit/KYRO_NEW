"""
routers/change_management.py — Regulatory change log and maker-checker rule
changes (Phase 11.5).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_role
from app.models.change_management import RegulatoryChange, RuleConfigChange
from app.models.regulatory_notice import RegulatoryNotice
from app.models.user import User
from app.routers.rule_configs import _validate_value
from app.services import change_service, federal_register_service
from app.services.change_service import ChangeError

router = APIRouter(prefix="/api/v1/changes", tags=["change-management"], dependencies=[Depends(get_current_user)])


class RegulatoryChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    section_ref: str
    heading: str | None = None
    change_type: str
    old_version: str | None = None
    new_version: str | None = None
    affected: dict[str, Any]
    status: str
    assessment_notes: str | None = None
    assessed_by: uuid.UUID | None = None
    assessed_at: datetime | None = None
    detected_at: datetime


class RegulatoryChangeDetail(RegulatoryChangeOut):
    diff: list[dict[str, str]]


class RegulatoryChangeAssess(BaseModel):
    status: Literal["ACTION_REQUIRED", "NO_ACTION", "CLOSED"]
    notes: str | None = Field(default=None, max_length=4000)


class RuleChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    jurisdiction: str
    previous_value: dict[str, Any]
    proposed_value: dict[str, Any]
    reason: str
    regulatory_change_id: uuid.UUID | None = None
    effective_from: date
    backtest: dict[str, Any] | None = None
    status: str
    proposed_by: uuid.UUID
    proposed_by_name: str | None = None
    proposed_at: datetime
    reviewed_by: uuid.UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    activated_at: datetime | None = None


class RuleChangePropose(BaseModel):
    key: str
    value: Any
    jurisdiction: str | None = None
    reason: str = Field(min_length=10, max_length=4000)
    effective_from: date
    regulatory_change_id: uuid.UUID | None = None


class RuleChangeBacktest(BaseModel):
    key: str
    value: Any
    jurisdiction: str | None = None


class RuleChangeReview(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "CANCELLED"]
    notes: str | None = Field(default=None, max_length=4000)


def _fail(exc: ChangeError) -> HTTPException:
    return HTTPException(exc.status_code, str(exc))


def _with_names(db: Session, changes: list[RuleConfigChange]) -> list[dict[str, Any]]:
    ids = {c.proposed_by for c in changes} | {c.reviewed_by for c in changes if c.reviewed_by}
    names = {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(ids))} if ids else {}
    out = []
    for c in changes:
        row = RuleChangeOut.model_validate(c).model_dump()
        row["proposed_by_name"] = names.get(c.proposed_by)
        row["reviewed_by_name"] = names.get(c.reviewed_by)
        out.append(row)
    return out


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, int]:
    return change_service.open_change_counts(db)


# ── Regulatory changes ───────────────────────────────────────────────────

@router.get("/regulatory", response_model=list[RegulatoryChangeOut])
def list_regulatory_changes(status_filter: str | None = None, db: Session = Depends(get_db)) -> list[RegulatoryChange]:
    query = db.query(RegulatoryChange)
    if status_filter:
        query = query.filter(RegulatoryChange.status == status_filter)
    return query.order_by(RegulatoryChange.detected_at.desc(), RegulatoryChange.section_ref).limit(200).all()


@router.get("/regulatory/{change_id}", response_model=RegulatoryChangeDetail)
def get_regulatory_change(change_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    change = db.get(RegulatoryChange, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regulatory change not found")
    return {**RegulatoryChangeOut.model_validate(change).model_dump(), "diff": change_service.text_diff(db, change)}


@router.put("/regulatory/{change_id}/assess", response_model=RegulatoryChangeOut)
def assess_regulatory_change(
    change_id: uuid.UUID,
    data: RegulatoryChangeAssess,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> RegulatoryChange:
    change = db.get(RegulatoryChange, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regulatory change not found")
    return change_service.assess_change(db, change, status=data.status, notes=data.notes, user_id=user.id)


# ── Rule changes ─────────────────────────────────────────────────────────

@router.get("/rules", response_model=list[RuleChangeOut])
def list_rule_changes(status_filter: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    change_service.activate_due(db)  # scheduled changes take effect even without the background worker
    query = db.query(RuleConfigChange)
    if status_filter:
        query = query.filter(RuleConfigChange.status == status_filter)
    return _with_names(db, query.order_by(RuleConfigChange.proposed_at.desc()).limit(200).all())


@router.post("/rules/backtest")
def backtest_rule_change(
    data: RuleChangeBacktest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> dict[str, Any]:
    """Preview a change's effect without proposing it."""
    _validate_value(data.key, data.value)
    scope = (data.jurisdiction or "GLOBAL").strip().upper()
    current = change_service.current_value(db, data.key, scope)
    return {"key": data.key, "jurisdiction": scope, "current_value": current,
            "backtest": change_service.backtest(db, data.key, current, data.value)}


@router.post("/rules", response_model=RuleChangeOut, status_code=status.HTTP_201_CREATED)
def propose_rule_change(
    data: RuleChangePropose,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> dict[str, Any]:
    _validate_value(data.key, data.value)
    try:
        change = change_service.propose_rule_change(
            db, key=data.key, value=data.value, jurisdiction=data.jurisdiction, reason=data.reason.strip(),
            effective_from=data.effective_from, regulatory_change_id=data.regulatory_change_id, user_id=user.id,
        )
    except ChangeError as exc:
        raise _fail(exc) from None
    return _with_names(db, [change])[0]


@router.put("/rules/{change_id}/review", response_model=RuleChangeOut)
def review_rule_change(
    change_id: uuid.UUID,
    data: RuleChangeReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> dict[str, Any]:
    change = db.get(RuleConfigChange, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule change not found")
    try:
        change = change_service.review_rule_change(db, change, decision=data.decision, notes=data.notes, user_id=user.id)
    except ChangeError as exc:
        raise _fail(exc) from None
    return _with_names(db, [change])[0]


# ── Federal Register notices ─────────────────────────────────────────────

class NoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_number: str
    title: str
    notice_type: str
    action: str | None = None
    abstract: str | None = None
    agencies: list[str]
    publication_date: date
    effective_on: date | None = None
    comments_close_on: date | None = None
    url: str
    matched_parts: list[str]
    status: str
    assessment_notes: str | None = None
    assessed_at: datetime | None = None


class NoticeAssess(BaseModel):
    status: Literal["ACTION_REQUIRED", "NO_ACTION", "CLOSED"]
    notes: str | None = Field(default=None, max_length=4000)


@router.get("/notices", response_model=list[NoticeOut])
def list_notices(status_filter: str | None = None, db: Session = Depends(get_db)) -> list[RegulatoryNotice]:
    query = db.query(RegulatoryNotice)
    if status_filter:
        query = query.filter(RegulatoryNotice.status == status_filter)
    return query.order_by(RegulatoryNotice.publication_date.desc(), RegulatoryNotice.document_number.desc()).limit(200).all()


@router.post("/notices/sync")
def sync_notices(
    db: Session = Depends(get_db), user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER"))
) -> dict[str, Any]:
    """Fetch rules and proposed rules from the Federal Register for every loaded CFR part."""
    return federal_register_service.sync(db)


@router.put("/notices/{notice_id}/assess", response_model=NoticeOut)
def assess_notice(
    notice_id: uuid.UUID,
    data: NoticeAssess,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN", "COMPLIANCE_OFFICER")),
) -> RegulatoryNotice:
    notice = db.get(RegulatoryNotice, notice_id)
    if notice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notice not found")
    return federal_register_service.assess(db, notice, status=data.status, notes=data.notes, user_id=user.id)
