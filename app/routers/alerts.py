"""
routers/alerts.py — Analyst alert work queue: assign, resolve, escalate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_role
from app.models.alert import Alert as AlertModel
from app.models.user import User
from app.schemas.alert import AlertAssign, AlertEscalate, AlertOut, AlertResolve
from app.schemas.common import Page
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"], dependencies=[Depends(get_current_user)])


def _get_alert_or_404(db: Session, alert_id: uuid.UUID) -> AlertModel:
    alert = db.get(AlertModel, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


@router.get("", response_model=Page[AlertOut])
def list_alerts(
    pagination: PaginationParams = Depends(),
    status_filter: str | None = None,
    customer_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
) -> Page[AlertOut]:
    query = db.query(AlertModel)
    if status_filter:
        query = query.filter(AlertModel.status == status_filter)
    if customer_id:
        query = query.filter(AlertModel.customer_id == customer_id)
    total = query.count()
    items = query.order_by(AlertModel.created_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db)) -> AlertModel:
    return _get_alert_or_404(db, alert_id)


@router.put("/{alert_id}/assign", response_model=AlertOut)
def assign(
    alert_id: uuid.UUID,
    data: AlertAssign,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ANALYST", "COMPLIANCE_OFFICER", "ADMIN")),
) -> AlertModel:
    alert = _get_alert_or_404(db, alert_id)
    alert.assigned_to = data.assigned_to
    alert.status = "ASSIGNED"
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="UPDATE", performed_by=user.id, new_values={"assigned_to": str(data.assigned_to)})
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}/resolve", response_model=AlertOut)
def resolve(
    alert_id: uuid.UUID,
    data: AlertResolve,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("COMPLIANCE_OFFICER", "ADMIN")),
) -> AlertModel:
    alert = _get_alert_or_404(db, alert_id)
    alert.status = "RESOLVED"
    alert.resolution_notes = data.resolution_notes
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = user.id
    if data.is_false_positive is not None:
        alert.is_false_positive = data.is_false_positive
    log_action(
        db,
        entity_type="ALERT",
        entity_id=alert.id,
        action="APPROVE",
        performed_by=user.id,
        new_values={"resolution_notes": data.resolution_notes, "is_false_positive": data.is_false_positive},
    )
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}/escalate", response_model=AlertOut)
def escalate(
    alert_id: uuid.UUID,
    data: AlertEscalate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ANALYST", "COMPLIANCE_OFFICER", "ADMIN")),
) -> AlertModel:
    alert = _get_alert_or_404(db, alert_id)
    alert.status = "ESCALATED"
    if data.resolution_notes:
        alert.resolution_notes = data.resolution_notes
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="UPDATE", performed_by=user.id, new_values={"status": "ESCALATED"})
    db.commit()
    db.refresh(alert)
    return alert
