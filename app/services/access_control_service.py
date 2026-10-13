"""
services/access_control_service.py — Emergency access to a case, and approval
of roles that can see SAR cases (models/access_control.py).

Both are four-eyes decisions: the approver must not be the person asking or the
person who would receive the access. Emergency access is approved by holders of
"sar.grant_access" (the MLRO); a role that can see SAR cases also by holders of
"roles.approve_sar" (administrators and the MLRO).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.access_control import EmergencyAccessGrant, RoleGrantRequest
from app.models.alert import Alert
from app.models.user import User
from app.permissions import ROLES, has_permission
from app.services.audit_service import log_action

GRANT_PERMISSION = "sar.grant_access"
ROLE_APPROVE_PERMISSIONS = (GRANT_PERMISSION, "roles.approve_sar")


class AccessError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _approver_check(approver: User, *others: uuid.UUID, permissions: tuple[str, ...] = (GRANT_PERMISSION,)) -> None:
    if not any(has_permission(approver.role, p) for p in permissions):
        raise AccessError("Your role cannot approve access to SAR cases", 403)
    if approver.id in others:
        raise AccessError("This must be decided by someone other than the person who asked or who would receive the access", 403)


# ── Emergency access ─────────────────────────────────────────────────────

def is_live(grant: EmergencyAccessGrant) -> bool:
    return grant.status == "APPROVED" and grant.expires_at is not None and grant.expires_at > _now()


def request_emergency(db: Session, user: User, alert_id: uuid.UUID, reason: str, duration_minutes: int) -> EmergencyAccessGrant:
    limit = get_settings().emergency_access_max_minutes
    if not 0 < duration_minutes <= limit:
        raise AccessError(f"Emergency access can last at most {limit} minutes", 422)
    if has_permission(user.role, "sar.view"):
        raise AccessError("Your role can already open this case")
    pending = db.query(EmergencyAccessGrant).filter(
        EmergencyAccessGrant.user_id == user.id, EmergencyAccessGrant.alert_id == alert_id,
        EmergencyAccessGrant.status.in_(("REQUESTED", "APPROVED")),
    ).all()
    if any(g.status == "REQUESTED" or is_live(g) for g in pending):
        raise AccessError("You already have a request or live access for this case")
    grant = EmergencyAccessGrant(user_id=user.id, alert_id=alert_id, reason=reason.strip(), duration_minutes=duration_minutes)
    db.add(grant)
    db.flush()
    log_action(db, entity_type="EMERGENCY_ACCESS", entity_id=grant.id, action="CREATE", performed_by=user.id,
               new_values={"alert_id": str(alert_id), "reason": grant.reason, "duration_minutes": duration_minutes})
    db.commit()
    db.refresh(grant)
    return grant


def decide_emergency(db: Session, approver: User, grant_id: uuid.UUID, approve: bool, notes: str | None) -> EmergencyAccessGrant:
    grant = db.get(EmergencyAccessGrant, grant_id)
    if grant is None:
        raise AccessError("Request not found", 404)
    _approver_check(approver, grant.user_id)
    if grant.status != "REQUESTED":
        raise AccessError("This request has already been decided")
    if approve and db.get(Alert, grant.alert_id) is None:
        raise AccessError("There is no case with that ID", 404)
    now = _now()
    grant.status = "APPROVED" if approve else "REJECTED"
    grant.decided_by, grant.decided_at, grant.decision_notes = approver.id, now, notes
    if approve:
        grant.expires_at = now + timedelta(minutes=grant.duration_minutes)
    log_action(db, entity_type="EMERGENCY_ACCESS", entity_id=grant.id, action="APPROVE" if approve else "REJECT",
               performed_by=approver.id,
               new_values={"notes": notes, "expires_at": grant.expires_at.isoformat() if grant.expires_at else None})
    db.commit()
    db.refresh(grant)
    return grant


def revoke_emergency(db: Session, user: User, grant_id: uuid.UUID) -> EmergencyAccessGrant:
    grant = db.get(EmergencyAccessGrant, grant_id)
    if grant is None or (grant.user_id != user.id and not has_permission(user.role, GRANT_PERMISSION)):
        raise AccessError("Request not found", 404)
    if grant.status == "REQUESTED":
        grant.status = "REVOKED"
    elif is_live(grant):
        grant.status = "REVOKED"
        grant.expires_at = _now()
    else:
        raise AccessError("This access is no longer active")
    grant.revoked_by, grant.revoked_at = user.id, _now()
    log_action(db, entity_type="EMERGENCY_ACCESS", entity_id=grant.id, action="UPDATE", performed_by=user.id,
               new_values={"status": "REVOKED"})
    db.commit()
    db.refresh(grant)
    return grant


def live_grant(db: Session, user: User, alert_id: uuid.UUID) -> EmergencyAccessGrant | None:
    grants = db.query(EmergencyAccessGrant).filter(
        EmergencyAccessGrant.user_id == user.id, EmergencyAccessGrant.alert_id == alert_id,
        EmergencyAccessGrant.status == "APPROVED", EmergencyAccessGrant.expires_at > _now(),
    ).all()
    return grants[0] if grants else None


def record_use(db: Session, user: User, grant: EmergencyAccessGrant) -> None:
    log_action(db, entity_type="EMERGENCY_ACCESS", entity_id=grant.id, action="VIEW", performed_by=user.id,
               new_values={"alert_id": str(grant.alert_id)})
    db.commit()


# ── Roles that can see SAR cases ─────────────────────────────────────────

def can_approve_roles(role: str) -> bool:
    return any(has_permission(role, p) for p in ROLE_APPROVE_PERMISSIONS)


def needs_approval(db: Session, role: str, requester: User) -> bool:
    """
    A role that can see SAR cases is granted only with a second person's approval.
    When nobody other than the person asking could approve it (a new installation
    with one administrator), there is nobody to ask, so it is granted directly and audited.
    """
    if not has_permission(role, "sar.view"):
        return False
    approver_roles = [code for code in ROLES if can_approve_roles(code)]
    return db.query(User.id).filter(
        User.role.in_(approver_roles), User.is_active.is_(True), User.id != requester.id,
    ).first() is not None


def request_role(db: Session, requester: User, user: User, to_role: str, reason: str | None) -> RoleGrantRequest:
    if db.query(RoleGrantRequest).filter(RoleGrantRequest.user_id == user.id, RoleGrantRequest.status == "REQUESTED").first():
        raise AccessError("A role change for this user is already waiting for approval")
    grant = RoleGrantRequest(user_id=user.id, from_role=user.role, to_role=to_role, reason=reason, requested_by=requester.id)
    db.add(grant)
    db.flush()
    log_action(db, entity_type="USER", entity_id=user.id, action="CREATE", performed_by=requester.id,
               new_values={"role_requested": to_role, "role_request_id": str(grant.id)})
    db.commit()
    db.refresh(grant)
    return grant


def decide_role(db: Session, approver: User, request_id: uuid.UUID, approve: bool, notes: str | None) -> RoleGrantRequest:
    grant = db.get(RoleGrantRequest, request_id)
    if grant is None:
        raise AccessError("Request not found", 404)
    _approver_check(approver, grant.requested_by, grant.user_id, permissions=ROLE_APPROVE_PERMISSIONS)
    if grant.status != "REQUESTED":
        raise AccessError("This request has already been decided")
    user = db.get(User, grant.user_id)
    if approve and user.role == "ADMIN" and user.is_active and not db.query(User.id).filter(
        User.role == "ADMIN", User.is_active.is_(True), User.id != user.id,
    ).first():
        raise AccessError("At least one active administrator is required")
    grant.status = "APPROVED" if approve else "REJECTED"
    grant.decided_by, grant.decided_at, grant.decision_notes = approver.id, _now(), notes
    if approve:
        old_role, user.role = user.role, grant.to_role
        log_action(db, entity_type="USER", entity_id=user.id, action="APPROVE", performed_by=approver.id,
                   old_values={"role": old_role}, new_values={"role": grant.to_role, "role_request_id": str(grant.id)})
    else:
        log_action(db, entity_type="USER", entity_id=user.id, action="REJECT", performed_by=approver.id,
                   new_values={"role_requested": grant.to_role, "role_request_id": str(grant.id), "notes": notes})
    db.commit()
    db.refresh(grant)
    return grant


def cancel_role(db: Session, user: User, request_id: uuid.UUID) -> RoleGrantRequest:
    grant = db.get(RoleGrantRequest, request_id)
    if grant is None:
        raise AccessError("Request not found", 404)
    if grant.status != "REQUESTED":
        raise AccessError("This request has already been decided")
    grant.status = "CANCELLED"
    grant.decided_by, grant.decided_at = user.id, _now()
    log_action(db, entity_type="USER", entity_id=grant.user_id, action="UPDATE", performed_by=user.id,
               new_values={"role_request_id": str(grant.id), "status": "CANCELLED"})
    db.commit()
    db.refresh(grant)
    return grant
