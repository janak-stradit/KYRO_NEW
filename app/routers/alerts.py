"""
routers/alerts.py — Analyst alert work queue: assign, resolve, escalate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncio
import json
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.deps import PaginationParams, get_current_user, require_role
from app.models.alert import Alert as AlertModel
from app.models.customer import Customer
from app.models.user import User
from app.schemas.alert import AlertAssign, AlertEscalate, AlertOut, AlertResolve
from app.schemas.common import Page
from app.services.audit_service import log_action
from app.utils.security import decode_token

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


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
    user: User = Depends(get_current_user),
) -> Page[AlertOut]:
    query = db.query(AlertModel)
    if status_filter:
        query = query.filter(AlertModel.status == status_filter)
    if customer_id:
        query = query.filter(AlertModel.customer_id == customer_id)
    total = query.count()
    items = query.order_by(AlertModel.created_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


def _get_user_from_token(token: str, db: Session) -> User:
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as e:
        print(f"[STREAM AUTH] JWT Decode Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: JWT decode error: {e}",
        )

    if payload.get("type") != "access":
        print(f"[STREAM AUTH] Invalid token type: {payload.get('type')}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: Not an access token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        print("[STREAM AUTH] User ID is None")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: User ID missing",
        )

    try:
        user = db.get(User, uuid.UUID(user_id))
    except Exception as e:
        print(f"[STREAM AUTH] DB Get Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: DB error: {e}",
        )

    if user is None:
        print(f"[STREAM AUTH] User not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: User not found",
        )
        
    if not user.is_active:
        print(f"[STREAM AUTH] User is inactive: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials: User inactive",
        )
    return user


@router.get("/stream")
async def stream_alerts(
    token: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # Authenticate query param token
    _get_user_from_token(token, db)

    async def event_generator():
        yield "event: heartbeat\ndata: {}\n\n"
        last_checked = datetime.now(timezone.utc)
        pulse_counter = 0

        while True:
            await asyncio.sleep(5)
            pulse_counter += 5
            now = datetime.now(timezone.utc)

            with SessionLocal() as session:
                new_alerts = (
                    session.query(AlertModel, Customer.full_name)
                    .join(Customer, AlertModel.customer_id == Customer.id)
                    .filter(AlertModel.created_at >= last_checked)
                    .order_by(AlertModel.created_at.asc())
                    .all()
                )

                for alert, full_name in new_alerts:
                    alert_data = {
                        "id": str(alert.id),
                        "customer_id": str(alert.customer_id),
                        "customer_name": full_name or "Unknown Customer",
                        "alert_type": alert.alert_type or "Behavioral Anomaly",
                        "risk_score": alert.risk_score,
                        "confidence": float(alert.confidence) if alert.confidence is not None else 0.85,
                        "created_at": alert.created_at.isoformat(),
                        "status": alert.status
                    }
                    yield f"event: alert\ndata: {json.dumps(alert_data)}\n\n"

                if pulse_counter % 20 == 0:
                    queue_size = session.query(AlertModel).filter(AlertModel.status == "OPEN").count()
                    status_data = {
                        "api_status": "healthy",
                        "queue_size": queue_size,
                        "model_status": "active"
                    }
                    yield f"event: system_status\ndata: {json.dumps(status_data)}\n\n"

            if pulse_counter % 15 == 0:
                yield "event: heartbeat\ndata: {}\n\n"

            last_checked = now

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AlertModel:
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
