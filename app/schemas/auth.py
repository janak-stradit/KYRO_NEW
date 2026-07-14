"""
schemas/auth.py — Login, token, and current-user schemas.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr

Role = Literal["ANALYST", "COMPLIANCE_OFFICER", "ADMIN"]


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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
    email: EmailStr
    full_name: str | None = None
    role: Role
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None
    password: str
    role: Role = "ANALYST"
