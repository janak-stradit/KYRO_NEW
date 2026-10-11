"""
routers/access_control.py — Emergency access to a case, and approval of roles
that can see SAR cases (services/access_control_service.py).
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_permission
from app.models.access_control import EmergencyAccessGrant, RoleGrantRequest
from app.models.user import User
from app.permissions import ROLES, has_permission
from app.services import access_control_service as svc

router = APIRouter(prefix="/api/v1/access", tags=["access-control"])


class EmergencyRequest(BaseModel):
    alert_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=2000)
    duration_minutes: int = Field(default=60, gt=0)


class Decision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=2000)


def _call(fn, *args):
    try:
        return fn(*args)
    except svc.AccessError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None


def _names(db: Session, ids: set) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    return {u.id: u.full_name or u.username for u in db.query(User).filter(User.id.in_(ids))} if ids else {}


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _grant_out(g: EmergencyAccessGrant, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(g.id), "alert_id": str(g.alert_id), "user_id": str(g.user_id), "user_name": names.get(g.user_id),
        "reason": g.reason, "duration_minutes": g.duration_minutes, "status": g.status, "live": svc.is_live(g),
        "requested_at": _iso(g.requested_at), "decided_by_name": names.get(g.decided_by), "decided_at": _iso(g.decided_at),
        "decision_notes": g.decision_notes, "expires_at": _iso(g.expires_at), "revoked_at": _iso(g.revoked_at),
    }


def _role_out(r: RoleGrantRequest, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(r.id), "user_id": str(r.user_id), "user_name": names.get(r.user_id),
        "from_role": r.from_role, "to_role": r.to_role, "to_role_label": ROLES[r.to_role].label if r.to_role in ROLES else r.to_role,
        "reason": r.reason, "status": r.status, "requested_by_name": names.get(r.requested_by), "requested_at": _iso(r.requested_at),
        "decided_by_name": names.get(r.decided_by), "decided_at": _iso(r.decided_at), "decision_notes": r.decision_notes,
    }


# ── Emergency access ─────────────────────────────────────────────────────

@router.post("/emergency", status_code=201)
def request_emergency(
    data: EmergencyRequest, db: Session = Depends(get_db), user: User = Depends(require_permission("emergency.request")),
) -> dict[str, Any]:
    """Ask for read-only access to one case for a limited time. The MLRO decides."""
    grant = _call(svc.request_emergency, db, user, data.alert_id, data.reason, data.duration_minutes)
    return _grant_out(grant, _names(db, {user.id}))


@router.get("/emergency")
def list_emergency(
    db: Session = Depends(get_db), user: User = Depends(require_permission("emergency.request", svc.GRANT_PERMISSION)),
) -> list[dict[str, Any]]:
    """Approvers see every request; anyone else sees their own."""
    query = db.query(EmergencyAccessGrant)
    if not has_permission(user.role, svc.GRANT_PERMISSION):
        query = query.filter(EmergencyAccessGrant.user_id == user.id)
    grants = query.order_by(EmergencyAccessGrant.requested_at.desc()).limit(200).all()
    names = _names(db, {g.user_id for g in grants} | {g.decided_by for g in grants})
    return [_grant_out(g, names) for g in grants]


@router.put("/emergency/{grant_id}/decision")
def decide_emergency(
    grant_id: uuid.UUID, data: Decision, db: Session = Depends(get_db),
    user: User = Depends(require_permission(svc.GRANT_PERMISSION)),
) -> dict[str, Any]:
    grant = _call(svc.decide_emergency, db, user, grant_id, data.decision == "APPROVED", data.notes)
    return _grant_out(grant, _names(db, {grant.user_id, grant.decided_by}))


@router.put("/emergency/{grant_id}/revoke")
def revoke_emergency(
    grant_id: uuid.UUID, db: Session = Depends(get_db),
    user: User = Depends(require_permission("emergency.request", svc.GRANT_PERMISSION)),
) -> dict[str, Any]:
    """End access early: the person who asked, or an approver."""
    grant = _call(svc.revoke_emergency, db, user, grant_id)
    return _grant_out(grant, _names(db, {grant.user_id, grant.decided_by}))


# ── Roles that can see SAR cases ─────────────────────────────────────────

@router.get("/role-requests")
def list_role_requests(
    db: Session = Depends(get_db), _: User = Depends(require_permission("users.manage", svc.GRANT_PERMISSION)),
) -> list[dict[str, Any]]:
    rows = db.query(RoleGrantRequest).order_by(RoleGrantRequest.requested_at.desc()).limit(200).all()
    names = _names(db, {r.user_id for r in rows} | {r.requested_by for r in rows} | {r.decided_by for r in rows})
    return [_role_out(r, names) for r in rows]


@router.put("/role-requests/{request_id}/decision")
def decide_role_request(
    request_id: uuid.UUID, data: Decision, db: Session = Depends(get_db),
    user: User = Depends(require_permission(svc.GRANT_PERMISSION)),
) -> dict[str, Any]:
    row = _call(svc.decide_role, db, user, request_id, data.decision == "APPROVED", data.notes)
    return _role_out(row, _names(db, {row.user_id, row.requested_by, row.decided_by}))


@router.put("/role-requests/{request_id}/cancel")
def cancel_role_request(
    request_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("users.manage")),
) -> dict[str, Any]:
    row = _call(svc.cancel_role, db, user, request_id)
    return _role_out(row, _names(db, {row.user_id, row.requested_by, row.decided_by}))
