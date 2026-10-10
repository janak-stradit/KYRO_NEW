"""
routers/alerts.py — Analyst alert work queue: assign, resolve, escalate.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import asyncio
import json
import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, SessionLocal
from app.deps import PaginationParams, get_current_user, require_permission
from app.models.alert import Alert as AlertModel
from app.models.customer import Customer
from app.models.alert_request import AlertRequest
from app.models.user import User
from app.permissions import has_permission, is_read_only
from app.visibility import alert_conditions, alert_visible, visible_alert_or_404
from app.schemas.alert import (
    OUTCOME_REASONS,
    RESOLUTION_OUTCOMES,
    RESOLUTION_REASONS,
    AlertAssign,
    AlertEscalate,
    AlertOut,
    AlertQA,
    AlertResolve,
    ResolutionOptions,
)
from app.schemas.common import Page
from app.services import customer_risk_service, feedback_service
from app.services.audit_service import log_action
from app.utils.security import decode_token

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"], dependencies=[Depends(require_permission("cases.view"))])
# The live stream authenticates from its query string, so it sits outside the header-based check
stream_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

_OUTCOME_PERMISSION = {
    "FALSE_POSITIVE": "alerts.close_false_positive",
    "TRUE_POSITIVE_NO_SAR": "alerts.close",
    "SAR_FILED": "sar.approve",
}


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
    query = db.query(AlertModel).filter(*alert_conditions(user))
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


@stream_router.get("/stream")
async def stream_alerts(
    token: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # EventSource cannot send headers, so the token arrives as a query parameter
    user = _get_user_from_token(token, db)
    if not has_permission(user.role, "cases.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

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
                    if not alert_visible(user, alert):
                        continue
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


def _target_days() -> dict[str, int]:
    settings = get_settings()
    return {"high": settings.case_target_days_high, "medium": settings.case_target_days_medium, "low": settings.case_target_days_low}


def _risk_band(score: int) -> str:
    return "high" if score >= 80 else "medium" if score >= 60 else "low"


def _overdue_condition():
    """Unresolved alerts older than the target for their risk band (CASE_TARGET_DAYS_*)."""
    now = datetime.now(timezone.utc)
    targets = _target_days()
    return and_(
        AlertModel.status.in_(_UNRESOLVED),
        or_(*(
            and_(AlertModel.risk_score >= low, AlertModel.risk_score < high, AlertModel.created_at < now - timedelta(days=targets[band] + 1))
            for band, (low, high) in _RISK_BANDS.items()
        )),
    )


def _awaiting_information_condition():
    return and_(
        AlertModel.status.in_(_UNRESOLVED),
        exists().where(AlertRequest.alert_id == AlertModel.id, AlertRequest.status == "OPEN"),
    )


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
    attention: str | None = None,
):
    """Alerts joined to their customer, narrowed by the work-queue filters."""
    query = db.query(AlertModel, Customer).join(Customer, AlertModel.customer_id == Customer.id).filter(*alert_conditions(user))
    if status_filter == "UNRESOLVED":
        query = query.filter(AlertModel.status.in_(_UNRESOLVED))
    elif status_filter == "AWAITING_QA":
        query = query.filter(AlertModel.status == "RESOLVED", AlertModel.qa_result.is_(None))
    elif status_filter == "QA_FAILED":
        query = query.filter(AlertModel.status == "RESOLVED", AlertModel.qa_result == "FAIL")
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
    if attention == "overdue":
        query = query.filter(_overdue_condition())
    elif attention == "awaiting_information":
        query = query.filter(_awaiting_information_condition())
    return query


@router.get("/queue")
def alert_queue(
    pagination: PaginationParams = Depends(),
    status_filter: str = Query("UNRESOLVED", pattern="^(UNRESOLVED|ALL|OPEN|ASSIGNED|IN_REVIEW|ESCALATED|RESOLVED|AWAITING_QA|QA_FAILED)$"),
    risk: str | None = Query(None, pattern="^(high|medium|low)$"),
    rule: str | None = Query(None, max_length=20),
    assignment: str | None = Query(None, pattern="^(unassigned|mine)$"),
    customer_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
    attention: str | None = Query(None, pattern="^(overdue|awaiting_information)$"),
    sort: str = Query("priority", pattern="^(priority|newest|oldest)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    The analyst work queue. Default order is highest risk first, then oldest,
    so the alert that most needs attention is always at the top.
    """
    query = _queue_filters(
        db, user, status_filter=status_filter, risk=risk, rule=rule, assignment=assignment, customer_id=customer_id, q=q,
        attention=attention,
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
        .filter(AlertModel.customer_id.in_(customer_ids), AlertModel.status.in_(_UNRESOLVED), *alert_conditions(user))
        .group_by(AlertModel.customer_id)
        .all()
    ) if customer_ids else {}
    assignee_ids = {alert.assigned_to for alert, _ in rows if alert.assigned_to}
    assignees = {
        u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(assignee_ids))
    } if assignee_ids else {}

    alert_ids = [alert.id for alert, _ in rows]
    open_requests: dict[uuid.UUID, tuple[int, int]] = {
        alert_id: (count, overdue or 0)
        for alert_id, count, overdue in db.query(
            AlertRequest.alert_id, func.count(AlertRequest.id),
            func.sum(case((AlertRequest.due_date < date.today(), 1), else_=0)),
        ).filter(AlertRequest.alert_id.in_(alert_ids), AlertRequest.status == "OPEN").group_by(AlertRequest.alert_id)
    } if alert_ids else {}
    targets = _target_days()
    now = datetime.now(timezone.utc)

    items = []
    for alert, customer in rows:
        item = AlertOut.model_validate(alert).model_dump(mode="json")
        target = targets[_risk_band(alert.risk_score)]
        age_days = ((alert.resolved_at or now) - alert.created_at).days
        requests_open, requests_overdue = open_requests.get(alert.id, (0, 0))
        item.update(
            age_days=age_days,
            target_days=target,
            overdue=alert.status in _UNRESOLVED and age_days > target,
            open_requests=requests_open,
            requests_overdue=int(requests_overdue),
            customer_name=customer.full_name,
            customer_pep=customer.pep_flag,
            customer_sanctions=customer.sanctions_flag,
            customer_open_alerts=open_per_customer.get(customer.id, 0),
            assigned_to_name=assignees.get(alert.assigned_to),
        )
        items.append(item)
    return {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get("/queue/customers")
def alert_queue_by_customer(
    pagination: PaginationParams = Depends(),
    risk: str | None = Query(None, pattern="^(high|medium|low)$"),
    rule: str | None = Query(None, max_length=20),
    assignment: str | None = Query(None, pattern="^(unassigned|mine)$"),
    q: str | None = Query(None, max_length=100),
    attention: str | None = Query(None, pattern="^(overdue|awaiting_information)$"),
    sort: str = Query("priority", pattern="^(priority|newest|oldest)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """
    The unresolved queue, one row per customer: how many alerts are open, the
    highest score, how long the oldest has waited and which rules fired. One
    review of the customer usually settles several alerts.
    """
    base = _queue_filters(
        db, user, status_filter="UNRESOLVED", risk=risk, rule=rule, assignment=assignment, customer_id=None, q=q, attention=attention,
    )
    alerts_count, top_score = func.count(AlertModel.id), func.max(AlertModel.risk_score)
    oldest, newest = func.min(AlertModel.created_at), func.max(AlertModel.created_at)
    groups = base.with_entities(
        Customer.id, alerts_count.label("alerts"), top_score.label("top"), oldest.label("oldest"),
        func.sum(case((AlertModel.risk_score >= 80, 1), else_=0)).label("high"),
        func.sum(case((_overdue_condition(), 1), else_=0)).label("overdue"),
        func.count(func.distinct(AlertModel.assigned_to)).label("owners"),
        func.sum(case((AlertModel.assigned_to.is_(None), 1), else_=0)).label("unassigned"),
    ).group_by(Customer.id)
    total = groups.count()
    order = {
        "priority": (top_score.desc(), alerts_count.desc(), oldest.asc(), Customer.id),
        "oldest": (oldest.asc(), Customer.id),
        "newest": (newest.desc(), Customer.id),
    }[sort]
    page = groups.order_by(*order).offset(pagination.offset).limit(pagination.limit).all()

    customer_ids = [row[0] for row in page]
    customers = {c.id: c for c in db.query(Customer).filter(Customer.id.in_(customer_ids))} if customer_ids else {}
    # The alerts behind each row, for the rules that fired, the owner and the case to open first
    details: dict[uuid.UUID, dict] = {cid: {"rules": {}, "owners": set(), "top": None} for cid in customer_ids}
    if customer_ids:
        for alert, _ in base.filter(AlertModel.customer_id.in_(customer_ids)).order_by(AlertModel.risk_score.desc(), AlertModel.created_at):
            d = details[alert.customer_id]
            if d["top"] is None:
                d["top"] = alert.id
            rules = alert.triggered_rules.get("rules") if isinstance(alert.triggered_rules, dict) else None
            for code in set(rules or []):
                d["rules"][str(code)] = d["rules"].get(str(code), 0) + 1
            if alert.assigned_to:
                d["owners"].add(alert.assigned_to)
    owner_ids = {o for d in details.values() for o in d["owners"]}
    names = {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(owner_ids))} if owner_ids else {}

    items = []
    for customer_id, alerts, top, oldest_at, high, overdue, _, unassigned in page:
        customer, d = customers.get(customer_id), details[customer_id]
        owners = sorted(names.get(o, "Unknown user") for o in d["owners"])
        items.append({
            "customer_id": str(customer_id), "customer_name": customer.full_name if customer else "Unknown customer",
            "customer_pep": bool(customer and customer.pep_flag), "customer_sanctions": bool(customer and customer.sanctions_flag),
            "customer_risk_level": customer.risk_level if customer else None,
            "open_alerts": alerts, "high_risk_alerts": int(high or 0), "overdue_alerts": int(overdue or 0),
            "unassigned_alerts": int(unassigned or 0), "max_risk_score": top, "oldest_created_at": oldest_at.isoformat(),
            "rules": [{"rule": r, "alerts": n} for r, n in sorted(d["rules"].items(), key=lambda kv: (-kv[1], kv[0]))],
            "owners": owners, "top_alert_id": str(d["top"]) if d["top"] else None,
        })
    return {"items": items, "total": total, "page": pagination.page, "page_size": pagination.page_size}


@router.get("/queue/summary")
def alert_queue_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    """Headline numbers for the work queue: what is waiting, how risky, how old, and where it concentrates."""
    unresolved = db.query(AlertModel).filter(AlertModel.status.in_(_UNRESOLVED), *alert_conditions(user))

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
        .filter(AlertModel.status.in_(_UNRESOLVED), *alert_conditions(user))
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
        "overdue": count(_overdue_condition()),
        "awaiting_information": count(_awaiting_information_condition()),
        "target_days": _target_days(),
        "oldest_created_at": unresolved.with_entities(func.min(AlertModel.created_at)).scalar(),
        "customers_with_alerts": unresolved.with_entities(func.count(func.distinct(AlertModel.customer_id))).scalar() or 0,
        "by_rule": [{"rule": r, "alerts": n} for r, n in sorted(rule_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        "top_customers": [
            {"customer_id": str(cid), "customer_name": name, "open_alerts": n, "max_risk_score": top}
            for cid, name, n, top in top_customers
        ],
    }


_CASE_WORK = ("alerts.close_false_positive", "alerts.close", "alerts.escalate", "sar.approve")


def _can_own_cases(role: str) -> bool:
    """A case needs an owner who can act on it: not a read-only role, and able to clear, close or escalate."""
    return not is_read_only(role) and any(has_permission(role, p) for p in _CASE_WORK)


@router.get("/assignees")
def list_assignees(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """Active users an alert can be assigned to."""
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name, User.username).all()
    return [{"id": str(u.id), "name": u.full_name or u.username, "role": u.role} for u in users if _can_own_cases(u.role)]


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
    user: User = Depends(require_permission("alerts.baseline")),
) -> dict:
    """False-positive rate, volumes and time-to-disposition, overall and per rule."""
    return feedback_service.disposition_baseline(db, days=days)


@router.get("/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AlertModel:
    return visible_alert_or_404(db, user, alert_id)


@router.put("/{alert_id}/assign", response_model=AlertOut)
def assign(
    alert_id: uuid.UUID,
    data: AlertAssign,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.assign")),
) -> AlertModel:
    alert = visible_alert_or_404(db, user, alert_id)
    assignee = db.get(User, data.assigned_to)
    if assignee is None or not assignee.is_active or not _can_own_cases(assignee.role):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Cases can only be assigned to an active user whose role works cases")
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
    user: User = Depends(require_permission("alerts.close_false_positive", "alerts.close", "sar.approve")),
) -> AlertModel:
    alert = visible_alert_or_404(db, user, alert_id)
    # Each outcome is its own decision: anyone on the queue may clear a false
    # positive, but only the MLRO (or an administrator) may approve a SAR.
    needed = _OUTCOME_PERMISSION[data.outcome]
    if not has_permission(user.role, needed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role cannot record the outcome {data.outcome}")
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
    # Closing an alert (or filing a SAR) can change the customer's rating
    customer = db.get(Customer, alert.customer_id)
    if customer is not None:
        customer_risk_service.assess_customer(db, customer, performed_by=user.id)
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}/qa", response_model=AlertOut)
def quality_check(
    alert_id: uuid.UUID,
    data: AlertQA,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.qa")),
) -> AlertModel:
    """Record whether a resolved case followed policy. The outcome itself is not changed."""
    alert = visible_alert_or_404(db, user, alert_id)
    if alert.status != "RESOLVED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a resolved case can be quality-checked")
    if alert.resolved_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A case must be quality-checked by someone other than the person who resolved it")
    alert.qa_result = data.result
    alert.qa_notes = data.notes
    alert.qa_by = user.id
    alert.qa_at = datetime.now(timezone.utc)
    log_action(db, entity_type="ALERT", entity_id=alert.id, action="REVIEW", performed_by=user.id,
               new_values={"qa_result": data.result, "qa_notes": data.notes})
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}/escalate", response_model=AlertOut)
def escalate(
    alert_id: uuid.UUID,
    data: AlertEscalate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("alerts.escalate")),
) -> AlertModel:
    alert = visible_alert_or_404(db, user, alert_id)
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
