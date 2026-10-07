"""
services/rule_config_service.py — resolves and edits the DB-backed rule
threshold overrides (Phase 4.4). Generic over whatever `defaults` dict the
caller supplies; rules_engine.py owns the actual default values and keys.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.rule_config import GLOBAL_JURISDICTION, RuleConfig
from app.services.audit_service import log_action

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, list[RuleConfig]]] = {}


def _load_active_rows(db: Session) -> list[RuleConfig]:
    """Session-independent short-TTL cache: thresholds change rarely, but
    evaluate() runs once per transaction, so we don't want a DB round trip
    on every scoring call."""
    cached = _cache.get("rows")
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]
    rows = db.query(RuleConfig).filter(RuleConfig.is_active.is_(True)).all()
    _cache["rows"] = (now, rows)
    return rows


def invalidate_cache() -> None:
    _cache.clear()


def _normalize_jurisdiction(jurisdiction: str | None) -> str | None:
    return jurisdiction.strip().upper() if jurisdiction else None


def get_effective_config(db: Session, defaults: dict[str, Any], jurisdiction: str | None) -> dict[str, Any]:
    """Layer DB overrides on top of `defaults`: GLOBAL row beats the
    hardcoded default, and a jurisdiction-specific row beats GLOBAL, for
    each key independently."""
    rows = _load_active_rows(db)
    jurisdiction = _normalize_jurisdiction(jurisdiction)

    resolved = dict(defaults)
    for row in rows:
        if row.jurisdiction == GLOBAL_JURISDICTION:
            resolved[row.key] = row.value["value"]
    if jurisdiction:
        for row in rows:
            if row.jurisdiction == jurisdiction:
                resolved[row.key] = row.value["value"]
    return resolved


def list_configs(db: Session, jurisdiction: str | None = None) -> list[RuleConfig]:
    query = db.query(RuleConfig)
    if jurisdiction:
        query = query.filter(RuleConfig.jurisdiction == _normalize_jurisdiction(jurisdiction))
    return query.order_by(RuleConfig.key, RuleConfig.jurisdiction).all()


def upsert_config(
    db: Session,
    *,
    key: str,
    value: Any,
    jurisdiction: str | None = None,
    description: str | None = None,
    performed_by: uuid.UUID | None = None,
) -> RuleConfig:
    scope = _normalize_jurisdiction(jurisdiction) or GLOBAL_JURISDICTION
    row = db.query(RuleConfig).filter(RuleConfig.key == key, RuleConfig.jurisdiction == scope).one_or_none()
    old_value = row.value["value"] if row else None

    if row is None:
        row = RuleConfig(key=key, jurisdiction=scope, value={"value": value}, description=description)
        db.add(row)
        action = "CREATE"
    else:
        row.value = {"value": value}
        row.is_active = True
        if description is not None:
            row.description = description
        action = "UPDATE"

    row.updated_by = performed_by
    db.flush()
    log_action(
        db,
        entity_type="RULE_CONFIG",
        entity_id=row.id,
        action=action,
        performed_by=performed_by,
        old_values={"value": old_value} if old_value is not None else None,
        new_values={"key": key, "jurisdiction": scope, "value": value},
    )
    db.commit()
    db.refresh(row)
    invalidate_cache()
    return row


def deactivate_config(db: Session, config_id: uuid.UUID, performed_by: uuid.UUID | None = None) -> RuleConfig | None:
    """Deactivating a row reverts that (key, jurisdiction) pair back to
    whatever the next layer down resolves to (GLOBAL, or the hardcoded
    default) rather than deleting audit history."""
    row = db.get(RuleConfig, config_id)
    if row is None:
        return None
    row.is_active = False
    row.updated_by = performed_by
    db.flush()
    log_action(db, entity_type="RULE_CONFIG", entity_id=row.id, action="DELETE", performed_by=performed_by)
    db.commit()
    invalidate_cache()
    return row
