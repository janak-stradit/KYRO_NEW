"""
services/policy_registry.py — Policies, besides detection rule thresholds, that
are stored as rule configs and changed through the maker-checker flow.

Each module provides defaults() and validate(key, value). rules_engine.DEFAULTS
is not listed here, to keep this module free of an import cycle; callers merge it.
"""
from __future__ import annotations

from typing import Any

from app.services import deadline_service, screening_policy

POLICY_MODULES = (deadline_service, screening_policy)


def policy_defaults() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for module in POLICY_MODULES:
        merged.update(module.defaults())
    return merged


def validate(key: str, value: Any) -> str | None:
    """Why `value` is not acceptable for the policy `key`, or None when it is (or the key is not a policy)."""
    for module in POLICY_MODULES:
        if key in module.defaults():
            return module.validate(key, value)
    return None
