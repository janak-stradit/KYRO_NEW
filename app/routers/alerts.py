"""
routers/alerts.py — Analyst alert work queue: assign, resolve, escalate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import asyncio
import json
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.deps import PaginationParams, get_current_user, require_role
from app.models.alert import Alert as AlertModel
from app.models.customer import Customer
from app.models.user import User
from app.schemas.alert import (
    OUTCOME_REASONS,
    RESOLUTION_OUTCOMES,
    RESOLUTION_REASONS,
    AlertAssign,
    AlertEscalate,
    AlertOut,
    AlertResolve,
    ResolutionOptions,
)
from app.schemas.common import Page
from app.services import feedback_service
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


_UNRESOLVED = ("OPEN", "ASSIGNED", "IN_REVIEW", "ESCALATED")
_RISK_BANDS = {"high": (80, 101), "medium": (60, 80), "low": (0, 60)}


def _queue_filters(
    db: Session,
    user: User,
    *,
    status_filter: str,
    risk: str | None,
    rule: str | None,
    assignment: str | None,
    customer_id: uuid.UUID | None,
    q: str | None,
):
    """Alerts joined to their customer, narrowed by the work-queue filters."""
    query = db.query(AlertModel, Customer).join(Customer, AlertModel.customer_id == Customer.id)
    if status_filter == "UNRESOLVED":
        query = query.filter(AlertModel.status.in_(_UNRESOLVED))
    elif status_filter != "ALL":
        query = query.filter(AlertModel.status == status_filter)
    if risk:
        low, high = _RISK_BANDS[risk]
        query = query.filter(AlertModel.risk_score >= low, AlertModel.risk_score < high)
    if rule:
        query = query.filter(AlertModel.triggered_rules["rules"].contains([rule]))
    if assignment == "unassigned":
        query = query.filter(AlertModel.assigned_to.is_(None))
    elif assignment == "mine":
        query = query.filter(AlertModel.assigned_to == user.id)
    if customer_id:
        query = query.filter(AlertModel.customer_id == customer_id)
    if q:
        query = query.filter(Customer.full_name.ilike(f"%{q.strip()}%"))
    return query


@router.get("/queue")
def alert_queue(
    pagination: PaginationParams = Depends(),
    status_filter: str = Query("UNRESOLVED", pattern="^(UNRESOLVED|ALL|OPEN|ASSIGNED|IN_REVIEW|ESCALATED|RESOLVED)$"),
    risk: str | None = Query(None, pattern="^(high|medium|low)$"),
    rule: str | None = Query(None, max_length=20),
    assignment: str | None = Query(None, pattern="^(unassigned|mine)$"),
    customer_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    sort: str = Query("priority", pattern="^(priority|newest|oldest)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    The analyst work queue. Default order is highest risk first, then oldest,
    so the alert that most needs attention is always at the top.
    """
    query = _queue_filters(
        db, user, status_filter=status_filter, risk=risk, rule=rule, assignment=assignment, customer_id=customer_id, q=q
    )
    total = query.count()
    order = {
        "priority": (AlertModel.risk_score.desc(), AlertModel.created_at.asc(), AlertModel.id),
        "newest": (AlertModel.created_at.desc(), AlertModel.id),
        "oldest": (AlertModel.created_at.asc(), AlertModel.id),
    }[sort]
    rows = query.order_by(*order).offset(pagination.offset).limit(pagination.limit).all()

    customer_ids = {customer.id for _, customer in rows}
    open_per_customer = dict(
        db.query(AlertModel.customer_id, func.count(AlertModel.id))
        .filter(AlertModel.customer_id.in_(customer_ids), AlertModel.status.in_(_UNRESOLVED))
        .group_by(AlertModel.customer_id)
        .all()
    ) if customer_ids else {}
    assignee_ids = {alert.assigned_to for alert, _ in rows if alert.assigned_to}
    assignees = {
        u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(assignee_ids))
    } if assignee_ids else {}

    items = []
    for alert, customer in rows:
        item = AlertOut.model_validate(alert).model_dump(mode="json")
        item.update(
            customer_name=customer.full_name,
            customer_pep=customer.pep_flag,
            customer_sanctions=customer.sanctions_flag,
            customer_open_alerts=open_per_customer.get(customer.id, 0),
            assigned_to_name=assignees.get(alert.assigned_to),
        )
        items.append(item)
    return {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get("/queue/summary")
def alert_queue_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Headline numbers for the work queue: what is waiting, how risky, how old, and where it concentrates."""
    unresolved = db.query(AlertModel).filter(AlertModel.status.in_(_UNRESOLVED))

    def count(*conditions) -> int:
        return unresolved.filter(*conditions).count()

    rule_counts: dict[str, int] = {}
    for (rules,) in unresolved.with_entities(AlertModel.triggered_rules):
        rules = rules.get("rules") if isinstance(rules, dict) else rules
        for code in set(rules or []) if isinstance(rules, list) else ():
            rule_counts[str(code)] = rule_counts.get(str(code), 0) + 1

    top_customers = (
        db.query(Customer.id, Customer.full_name, func.count(AlertModel.id), func.max(AlertModel.risk_score))
        .join(AlertModel, AlertModel.customer_id == Customer.id)
        .filter(AlertModel.status.in_(_UNRESOLVED))
        .group_by(Customer.id, Customer.full_name)
        .order_by(func.count(AlertModel.id).desc(), func.max(AlertModel.risk_score).desc())
        .limit(5)
        .all()
    )
    return {
        "unresolved": count(),
        "high_risk": count(AlertModel.risk_score >= 80),
        "unassigned": count(AlertModel.assigned_to.is_(None)),
        "assigned_to_me": count(AlertModel.assigned_to == user.id),
        "escalated": count(AlertModel.status == "ESCALATED"),
        "oldest_created_at": unresolved.with_entities(func.min(AlertModel.created_at)).scalar(),
        "customers_with_alerts": unresolved.with_entities(func.count(func.distinct(AlertModel.customer_id))).scalar() or 0,
        "by_rule": [{"rule": r, "alerts": n} for r, n in sorted(rule_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        "top_customers": [
            {"customer_id": str(cid), "customer_name": name, "open_alerts": n, "max_risk_score": top}
            for cid, name, n, top in top_customers
        ],
    }


@router.get("/assignees")
def list_assignees(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """Active users an alert can be assigned to."""
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name, User.username).all()
    return [{"id": str(u.id), "name": u.full_name or u.username, "role": u.role} for u in users]


@router.get("/resolution-options", response_model=ResolutionOptions)
def resolution_options(user: User = Depends(get_current_user)) -> dict:
    """Outcome and reason codes for the Resolve dialog."""
    return {
        "outcomes": [
            {"code": code, "label": label, "reasons": list(OUTCOME_REASONS[code])}
            for code, label in RESOLUTION_OUTCOMES.items()
        ],
        "reasons": [{"code": code, "label": label} for code, label in RESOLUTION_REASONS.items()],
    }


@router.get("/disposition-baseline")
def disposition_baseline(
    days: int = Query(90, ge=1, le=730),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("COMPLIANCE_OFFICER", "ADMIN")),
) -> dict:
    """False-positive rate, volumes and time-to-disposition, overall and per rule."""
    return feedback_service.disposition_baseline(db, days=days)


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
    if alert.status == "RESOLVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already resolved")
    alert.status = "RESOLVED"
    alert.resolution_notes = data.resolution_notes
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = user.id
    alert.resolution_outcome = data.outcome
    alert.resolution_reasons = data.reasons
    alert.sar_reference = data.sar_reference
    alert.is_false_positive = data.outcome == "FALSE_POSITIVE"
    log_action(
        db,
        entity_type="ALERT",
        entity_id=alert.id,
        action="APPROVE",
        performed_by=user.id,
        new_values={
            "resolution_outcome": data.outcome,
            "resolution_reasons": data.reasons,
            "resolution_notes": data.resolution_notes,
            "sar_reference": data.sar_reference,
            "is_false_positive": alert.is_false_positive,
        },
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
    if alert.status == "RESOLVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already resolved")
    alert.status = "ESCALATED"
    alert.resolution_outcome = "ESCALATED"
    alert.resolution_reasons = data.reasons or None
    if data.resolution_notes:
        alert.resolution_notes = data.resolution_notes
    log_action(
        db,
        entity_type="ALERT",
        entity_id=alert.id,
        action="UPDATE",
        performed_by=user.id,
        new_values={"status": "ESCALATED", "resolution_reasons": data.reasons},
    )
    db.commit()
    db.refresh(alert)
    return alert
