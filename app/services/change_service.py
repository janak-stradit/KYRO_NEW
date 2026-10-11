"""
services/change_service.py — Regulatory change management (Phase 11.5).

1. When ingestion finds a section added, amended or removed, `record_change`
   stores what changed and which obligations, controls and rule settings it
   touches (read from the 11.4 mappings).
2. A rule threshold change is proposed with a reason and an effective date,
   backtested against recent data, approved or rejected by a *different*
   person, and only then applied — on its effective date.
"""
from __future__ import annotations

import difflib
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.change_management import RegulatoryChange, RuleConfigChange
from app.models.obligation import Obligation
from app.models.obligation_mapping import ObligationMapping
from app.models.regulatory import RegulatoryIngestionRun, RegulatorySection, RegulatorySource
from app.models.rule_config import GLOBAL_JURISDICTION
from app.models.transaction import Transaction
from app.services import rule_config_service
from app.services.audit_service import log_action
from app.services.control_catalogue import CONTROLS_BY_CODE

BACKTEST_DAYS = 90


class ChangeError(ValueError):
    """A change request that cannot be carried out; `status_code` is the HTTP status to return."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


# ── Regulatory changes ───────────────────────────────────────────────────

def record_change(
    db: Session,
    source: RegulatorySource,
    run: RegulatoryIngestionRun,
    *,
    change_type: str,
    old_section: RegulatorySection | None = None,
    new_section: RegulatorySection | None = None,
) -> RegulatoryChange:
    """Call before the old section's obligations are superseded, so the impact is captured as it stood."""
    obligations = (
        db.query(Obligation)
        .filter(Obligation.section_id == old_section.id, Obligation.status.in_(("PROPOSED", "CONFIRMED")))
        .all()
        if old_section is not None else []
    )
    mappings = (
        db.query(ObligationMapping)
        .filter(ObligationMapping.obligation_id.in_([o.id for o in obligations]), ObligationMapping.status == "CONFIRMED")
        .all()
        if obligations else []
    )
    controls = sorted({m.control_code for m in mappings})
    section = new_section or old_section
    change = RegulatoryChange(
        source_id=source.id,
        run_id=run.id,
        section_ref=section.section_ref,
        heading=section.heading,
        change_type=change_type,
        old_section_id=old_section.id if old_section is not None else None,
        new_section_id=new_section.id if new_section is not None else None,
        old_version=old_section.version if old_section is not None else None,
        new_version=new_section.version if new_section is not None else None,
        affected={
            "obligations": [
                {"id": str(o.id), "obligated_party": o.obligated_party, "action": o.action, "status": o.status}
                for o in obligations
            ],
            "controls": [
                {"code": code, "name": CONTROLS_BY_CODE[code].name if code in CONTROLS_BY_CODE else code}
                for code in controls
            ],
            "config_keys": sorted({k for code in controls if code in CONTROLS_BY_CODE for k in CONTROLS_BY_CODE[code].config_keys}),
        },
    )
    db.add(change)
    return change


def _sentences(text: str | None) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;:])\s+|\n+", text or "") if s.strip()]


def text_diff(db: Session, change: RegulatoryChange) -> list[dict[str, str]]:
    """Sentence-level differences between the old and new text: [{"op": "removed" | "added", "text": ...}]."""
    old = db.get(RegulatorySection, change.old_section_id) if change.old_section_id else None
    new = db.get(RegulatorySection, change.new_section_id) if change.new_section_id else None
    before, after = _sentences(old.content if old else None), _sentences(new.content if new else None)
    out = []
    for line in difflib.ndiff(before, after):
        if line.startswith("- "):
            out.append({"op": "removed", "text": line[2:]})
        elif line.startswith("+ "):
            out.append({"op": "added", "text": line[2:]})
    return out


def assess_change(
    db: Session, change: RegulatoryChange, *, status: str, notes: str | None, user_id: uuid.UUID
) -> RegulatoryChange:
    old_status = change.status
    change.status = status
    change.assessment_notes = notes
    change.assessed_by = user_id
    change.assessed_at = datetime.now(timezone.utc)
    log_action(
        db, entity_type="REGULATORY_CHANGE", entity_id=change.id, action="REVIEW", performed_by=user_id,
        old_values={"status": old_status}, new_values={"status": status, "notes": notes},
    )
    db.commit()
    db.refresh(change)
    return change


# ── Rule config changes (maker-checker) ──────────────────────────────────

def current_value(db: Session, key: str, jurisdiction: str) -> Any:
    from app.services import policy_registry
    from app.services.rules_engine import DEFAULTS  # avoids an import cycle

    scope = None if jurisdiction == GLOBAL_JURISDICTION else jurisdiction
    return rule_config_service.get_effective_config(db, {**DEFAULTS, **policy_registry.policy_defaults()}, scope).get(key)


def backtest(db: Session, key: str, current: Any, proposed: Any) -> dict[str, Any]:
    """
    What the change would have done over the last 90 days. Implemented for
    the amount threshold, where it can be computed exactly from transaction
    amounts; other settings are reported as not backtested rather than guessed.
    """
    if key != "AMOUNT_THRESHOLD":
        return {"available": False, "reason": f"No backtest is implemented for {key}; review the change manually."}

    cutoff = datetime.now(timezone.utc) - timedelta(days=BACKTEST_DAYS)
    recent = db.query(Transaction).filter(Transaction.transaction_date >= cutoff)

    def flagged(threshold: Any) -> int:
        return recent.filter(Transaction.amount > threshold).count()

    low, high = sorted((float(current), float(proposed)))
    between = recent.filter(Transaction.amount > low, Transaction.amount <= high)
    # Customers with a confirmed true positive on the amount rule whose flagged
    # transactions fall in the band the change would stop (or start) flagging
    true_positive_customers = {
        row[0]
        for row in db.query(Alert.customer_id).filter(
            Alert.resolution_outcome.in_(("SAR_FILED", "TRUE_POSITIVE_NO_SAR")),
            Alert.triggered_rules["rules"].contains(["R001"]),
        )
    }
    affected_customers = {row[0] for row in between.with_entities(Transaction.customer_id).distinct()}
    loosening = float(proposed) > float(current)
    missed = len(true_positive_customers & affected_customers) if loosening else 0
    now, after = flagged(current), flagged(proposed)
    return {
        "available": True,
        "window_days": BACKTEST_DAYS,
        "transactions_flagged_now": now,
        "transactions_flagged_after": after,
        "difference": after - now,
        "customers_affected": len(affected_customers),
        "confirmed_true_positive_customers_missed": missed,
        "passes_recall_floor": missed == 0,
        "scope_note": "Counts all transactions in the window, regardless of jurisdiction.",
    }


def propose_rule_change(
    db: Session,
    *,
    key: str,
    value: Any,
    jurisdiction: str | None,
    reason: str,
    effective_from: date,
    regulatory_change_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> RuleConfigChange:
    scope = (jurisdiction or GLOBAL_JURISDICTION).strip().upper()
    existing = current_value(db, key, scope)
    if existing == value:
        raise ChangeError(f"{key} is already set to that value")
    if db.query(RuleConfigChange).filter(
        RuleConfigChange.key == key, RuleConfigChange.jurisdiction == scope,
        RuleConfigChange.status.in_(("PENDING_APPROVAL", "APPROVED")),
    ).first():
        raise ChangeError(f"A change to {key} is already waiting for approval or activation")
    if regulatory_change_id and db.get(RegulatoryChange, regulatory_change_id) is None:
        raise ChangeError("Regulatory change not found", 404)

    change = RuleConfigChange(
        key=key, jurisdiction=scope, previous_value={"value": existing}, proposed_value={"value": value},
        reason=reason, regulatory_change_id=regulatory_change_id, effective_from=effective_from,
        backtest=backtest(db, key, existing, value), proposed_by=user_id,
    )
    db.add(change)
    db.flush()
    log_action(
        db, entity_type="RULE_CONFIG_CHANGE", entity_id=change.id, action="CREATE", performed_by=user_id,
        new_values={"key": key, "jurisdiction": scope, "from": existing, "to": value, "effective_from": effective_from.isoformat()},
    )
    db.commit()
    db.refresh(change)
    return change


def _activate(db: Session, change: RuleConfigChange) -> None:
    rule_config_service.upsert_config(
        db, key=change.key, value=change.proposed_value["value"],
        jurisdiction=change.jurisdiction, performed_by=change.reviewed_by,
    )
    change.status = "ACTIVE"
    change.activated_at = datetime.now(timezone.utc)
    db.commit()


def review_rule_change(
    db: Session, change: RuleConfigChange, *, decision: str, notes: str | None, user_id: uuid.UUID
) -> RuleConfigChange:
    if change.status != "PENDING_APPROVAL":
        raise ChangeError(f"This change is {change.status.replace('_', ' ').lower()} and can no longer be reviewed")
    if decision == "CANCELLED":
        if user_id != change.proposed_by:
            raise ChangeError("Only the person who proposed a change can withdraw it", 403)
    elif user_id == change.proposed_by:
        # The whole point of maker-checker: the proposer cannot approve their own change
        raise ChangeError("A change must be approved or rejected by someone other than the person who proposed it", 403)
    if decision == "REJECTED" and not (notes or "").strip():
        raise ChangeError("Give a reason when rejecting a change", 422)

    change.status = decision
    change.reviewed_by = user_id
    change.reviewed_at = datetime.now(timezone.utc)
    change.review_notes = notes
    log_action(
        db, entity_type="RULE_CONFIG_CHANGE", entity_id=change.id,
        action={"APPROVED": "APPROVE", "REJECTED": "REJECT"}.get(decision, "UPDATE"),
        performed_by=user_id, new_values={"status": decision, "notes": notes},
    )
    db.commit()
    if decision == "APPROVED" and change.effective_from <= date.today():
        _activate(db, change)
    db.refresh(change)
    return change


def activate_due(db: Session) -> int:
    """Apply approved changes whose effective date has arrived. Safe to call often."""
    due = (
        db.query(RuleConfigChange)
        .filter(RuleConfigChange.status == "APPROVED", RuleConfigChange.effective_from <= date.today())
        .order_by(RuleConfigChange.effective_from, RuleConfigChange.proposed_at)
        .all()
    )
    for change in due:
        _activate(db, change)
    return len(due)


def open_change_counts(db: Session) -> dict[str, int]:
    return {
        "regulatory_open": db.query(func.count(RegulatoryChange.id)).filter(RegulatoryChange.status.in_(("OPEN", "ACTION_REQUIRED"))).scalar() or 0,
        "rule_changes_pending": db.query(func.count(RuleConfigChange.id)).filter(RuleConfigChange.status == "PENDING_APPROVAL").scalar() or 0,
        "rule_changes_scheduled": db.query(func.count(RuleConfigChange.id)).filter(RuleConfigChange.status == "APPROVED").scalar() or 0,
    }
