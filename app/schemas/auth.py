"""
schemas/auth.py — Login, token, and current-user schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = str  # one of app.permissions.ROLE_CODES


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    sub: str
    role: Role | None = None
    type: Literal["access", "refresh"] = "access"
    exp: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    # Plain str on output: stored addresses were validated on input, and
    # re-validating them here turns e.g. the seeded "admin@kyro.local"
    # (a reserved TLD) into a 500 on /auth/me.
    email: str
    full_name: str | None = None
    role: Role
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime


class CurrentUser(UserOut):
    role_label: str
    permissions: list[str]


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None
    password: str
    role: Role = "ANALYST"
