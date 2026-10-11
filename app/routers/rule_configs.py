"""
routers/rule_configs.py — view and edit the rules engine's DB-backed
threshold overrides (Phase 4.4). Any authenticated user can read; only
roles holding "rules.edit_direct" can write, and every write is audit-logged via
rule_config_service.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.rule_config import RuleConfig
from app.models.user import User
from app.schemas.rule_config import RuleConfigOut, RuleConfigUpdate
from app.services import deadline_service, rule_config_service
from app.services.rules_engine import DEFAULTS as RULE_DEFAULTS


def all_defaults() -> dict[str, Any]:
    """Every editable setting: detection rule thresholds and deadline policy."""
    return {**RULE_DEFAULTS, **deadline_service.defaults()}

router = APIRouter(prefix="/api/v1/rule-configs", tags=["rule-configs"], dependencies=[Depends(get_current_user)])

_NUMERIC_KEYS = {
    "AMOUNT_THRESHOLD",
    "VELOCITY_DAILY_LIMIT",
    "VELOCITY_HOURLY_LIMIT",
    "RAPID_SUCCESSION_WINDOW_SECONDS",
    "ALERT_THRESHOLD",
    "EDD_THRESHOLD",
}
_SEVERITY_KEYS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_value(key: str, value: Any) -> None:
    defaults = all_defaults()
    if key not in defaults:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown rule config key '{key}'. Valid keys: {sorted(defaults)}")
    if key not in RULE_DEFAULTS:
        problem = deadline_service.validate(key, value)
        if problem:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    elif key in _NUMERIC_KEYS:
        if not _is_number(value):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{key} must be a number")
    elif key == "HIGH_RISK_COUNTRIES":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "HIGH_RISK_COUNTRIES must be a list of strings")
    elif key == "SEVERITY_WEIGHT":
        if not isinstance(value, dict) or set(value.keys()) != _SEVERITY_KEYS or not all(_is_number(v) for v in value.values()):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "SEVERITY_WEIGHT must be an object with exactly LOW/MEDIUM/HIGH/CRITICAL numeric values",
            )


@router.get("", response_model=list[RuleConfigOut])
def list_configs(jurisdiction: str | None = None, db: Session = Depends(get_db)) -> list[RuleConfig]:
    return rule_config_service.list_configs(db, jurisdiction=jurisdiction)


@router.get("/effective", response_model=dict[str, Any])
def effective_config(jurisdiction: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The merged config a transaction for this jurisdiction would actually
    be scored against right now (defaults <- GLOBAL <- jurisdiction)."""
    return rule_config_service.get_effective_config(db, all_defaults(), jurisdiction)


@router.put("/{key}", response_model=RuleConfigOut)
def upsert(
    key: str,
    data: RuleConfigUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rules.edit_direct")),
) -> RuleConfig:
    _validate_value(key, data.value)
    if get_settings().rule_changes_require_approval:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Rule thresholds change through an approved change request (/api/v1/changes/rules)"
        )
    return rule_config_service.upsert_config(
        db,
        key=key,
        value=data.value,
        jurisdiction=data.jurisdiction,
        description=data.description,
        performed_by=user.id,
    )


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(
    config_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rules.edit_direct")),
) -> None:
    row = rule_config_service.deactivate_config(db, config_id, performed_by=user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule config not found")
