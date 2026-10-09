"""
routers/auth.py — JWT login/logout/refresh and current-user endpoints.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.permissions import ROLES, permissions_for
from app.rate_limit import limiter
from app.schemas.auth import RefreshRequest, Token, UserCreate, UserOut, CurrentUser
from app.utils.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    if not get_settings().allow_self_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Self-registration is turned off. Ask an administrator for an account.")
    if db.query(User).filter(User.username == data.username).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    if db.query(User).filter(User.email == data.email).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    # Self-service registration always gets the least-privileged role —
    # COMPLIANCE_OFFICER/ADMIN must be granted out-of-band, otherwise
    # anyone could hand themselves admin rights via this open endpoint.
    user = User(
        username=data.username,
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role="ANALYST",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(get_settings().rate_limit_login)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.username == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")

    user.last_login = datetime.now(timezone.utc)
    db.commit()

    return Token(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
    )


@router.post("/logout")
def logout(_: User = Depends(get_current_user)) -> dict[str, str]:
    # Stateless JWT: client discards tokens. Server-side revocation (e.g. a
    # denylist in Redis) is a hardening item for a later phase.
    return {"detail": "Logged out"}


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> Token:
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer active")

    return Token(
        access_token=create_access_token(str(user.id), user.role),
        refresh_token=create_refresh_token(str(user.id), user.role),
    )


@router.get("/me", response_model=CurrentUser)
def me(user: User = Depends(get_current_user)) -> dict:
    definition = ROLES.get(user.role)
    return {
        **UserOut.model_validate(user).model_dump(),
        "role_label": definition.label if definition else user.role,
        "permissions": sorted(permissions_for(user.role)),
    }
