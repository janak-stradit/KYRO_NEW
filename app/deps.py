"""
deps.py — FastAPI dependencies: DB session re-export, current-user auth, RBAC, pagination.
"""
from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, Query, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.permissions import has_permission, is_read_only
from app.utils.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    description="Click Authorize and enter a username/password (register one first via POST /api/v1/auth/register).",
)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_current_user(
    request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise credentials_error

    if payload.get("type") != "access":
        raise credentials_error

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error

    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise credentials_error
    # Read-only roles (auditor, executive viewer) cannot change anything,
    # whichever endpoint they reach. Signing out and token refresh still work.
    if (
        request.method not in _SAFE_METHODS
        and is_read_only(user.role)
        and not request.url.path.startswith("/api/v1/auth/")
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This role is read-only")
    return user


def require_permission(*permissions: str):
    """Allow the request if the user's role holds any one of `permissions`."""

    def _check(user: User = Depends(get_current_user)) -> User:
        if not any(has_permission(user.role, p) for p in permissions):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return _check


class PaginationParams:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=15000)):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size
