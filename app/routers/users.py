"""
routers/users.py — User administration, role definitions and the audit log.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_permission
from app.models.access_control import RoleGrantRequest
from app.models.audit import AuditLog
from app.models.user import User
from app.permissions import PERMISSIONS, ROLE_DEFINITIONS, ROLES
from app.services import access_control_service
from app.services.audit_service import log_action
from app.utils.security import hash_password

router = APIRouter(prefix="/api/v1", tags=["users"], dependencies=[Depends(get_current_user)])

MIN_PASSWORD_LENGTH = 10


def _valid_role(value: str | None) -> str | None:
    if value is not None and value not in ROLES:
        raise ValueError(f"Unknown role: {value}")
    return value


def _valid_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return value


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime
    pending_role: str | None = None  # a role change waiting for approval (roles that can see SAR cases)


class UserAdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # internal domains such as .local are allowed
    full_name: str = Field(min_length=1, max_length=255)
    password: str
    role: str

    _role = field_validator("role")(_valid_role)
    _password = field_validator("password")(_valid_password)


class UserAdminUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = None
    is_active: bool | None = None

    _role = field_validator("role")(_valid_role)


class PasswordReset(BaseModel):
    password: str

    _password = field_validator("password")(_valid_password)


def _user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


def _with_pending_role(db: Session, users: list[User]) -> list[UserAdminOut]:
    ids = [u.id for u in users]
    pending = dict(
        db.query(RoleGrantRequest.user_id, RoleGrantRequest.to_role)
        .filter(RoleGrantRequest.user_id.in_(ids), RoleGrantRequest.status == "REQUESTED")
    ) if ids else {}
    return [UserAdminOut.model_validate(u).model_copy(update={"pending_role": pending.get(u.id)}) for u in users]


def _other_active_admins(db: Session, user: User) -> int:
    return db.query(User).filter(User.role == "ADMIN", User.is_active.is_(True), User.id != user.id).count()


# ── Roles ────────────────────────────────────────────────────────────────

@router.get("/roles")
def list_roles() -> dict[str, Any]:
    """Every role with its purpose, responsibilities, limits and permissions."""
    return {
        "permissions": [{"code": code, "label": label} for code, label in PERMISSIONS.items()],
        "roles": [
            {
                "code": r.code, "label": r.label, "purpose": r.purpose, "responsibilities": list(r.responsibilities),
                "limits": list(r.limits), "permissions": sorted(r.permissions), "read_only": r.read_only, "legacy": r.legacy,
            }
            for r in ROLE_DEFINITIONS
        ],
    }


# ── Users ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_permission("users.manage"))) -> list[UserAdminOut]:
    return _with_pending_role(db, db.query(User).order_by(User.is_active.desc(), User.full_name, User.username).all())


@router.post("/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserAdminCreate, db: Session = Depends(get_db), admin: User = Depends(require_permission("users.manage"))
) -> User:
    if db.query(User).filter(User.username.ilike(data.username)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken")
    if db.query(User).filter(User.email.ilike(data.email)).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")
    if access_control_service.needs_approval(db, data.role, admin):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{ROLES[data.role].label} can see SAR cases, so it needs a second person's approval (another administrator or the MLRO). "
            "Create the user with another role first, then change the role.",
        )
    user = User(
        username=data.username, email=data.email, full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password), role=data.role, is_active=True,
    )
    db.add(user)
    db.flush()
    log_action(db, entity_type="USER", entity_id=user.id, action="CREATE", performed_by=admin.id,
               new_values={"username": user.username, "role": user.role})
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: uuid.UUID,
    data: UserAdminUpdate,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
) -> UserAdminOut:
    """Update a user. A role that can see SAR cases is not applied here: it waits for a second person's approval (202)."""
    user = _user_or_404(db, user_id)
    changes = data.model_dump(exclude_none=True)
    loses_admin = user.role == "ADMIN" and user.is_active and (
        changes.get("role", "ADMIN") != "ADMIN" or changes.get("is_active") is False
    )
    if loses_admin:
        # Never leave the system with nobody able to manage it
        if user.id == admin.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot remove your own administrator access")
        if _other_active_admins(db, user) == 0:
            raise HTTPException(status.HTTP_409_CONFLICT, "At least one active administrator is required")

    if changes.get("role", user.role) != user.role and access_control_service.needs_approval(db, changes["role"], admin):
        try:
            access_control_service.request_role(db, admin, user, changes.pop("role"), None)
        except access_control_service.AccessError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        response.status_code = status.HTTP_202_ACCEPTED

    old = {key: getattr(user, key) for key in changes}
    for key, value in changes.items():
        setattr(user, key, value.strip() if key == "full_name" else value)
    if changes != old:
        log_action(db, entity_type="USER", entity_id=user.id, action="UPDATE", performed_by=admin.id,
                   old_values=old, new_values=changes)
    db.commit()
    db.refresh(user)
    return _with_pending_role(db, [user])[0]


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    data: PasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(require_permission("users.manage")),
) -> None:
    user = _user_or_404(db, user_id)
    user.hashed_password = hash_password(data.password)
    log_action(db, entity_type="USER", entity_id=user.id, action="UPDATE", performed_by=admin.id,
               new_values={"password": "reset"})
    db.commit()


# ── Audit log ────────────────────────────────────────────────────────────

@router.get("/audit-logs")
def list_audit_logs(
    pagination: PaginationParams = Depends(),
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    performed_by: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("audit.read")),
) -> dict[str, Any]:
    """Who changed what and when, newest first."""
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if performed_by:
        query = query.filter(AuditLog.performed_by == performed_by)
    total = query.count()
    rows = query.order_by(AuditLog.performed_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    names = {
        u.id: u.full_name or u.username
        for u in db.query(User).filter(User.id.in_({r.performed_by for r in rows if r.performed_by}))
    } if rows else {}
    return {
        "total": total, "page": pagination.page, "page_size": pagination.page_size,
        "items": [
            {
                "id": str(r.id), "entity_type": r.entity_type, "entity_id": str(r.entity_id), "action": r.action,
                "performed_by": str(r.performed_by) if r.performed_by else None,
                "performed_by_name": names.get(r.performed_by) or ("System" if r.performed_by is None else "Unknown user"),
                "performed_at": r.performed_at.isoformat(), "old_values": r.old_values, "new_values": r.new_values,
            }
            for r in rows
        ],
    }
