"""
services/transaction_codes.py — A source system's own transaction codes mapped to
KYRO's type, direction and channel (rules engine R2).

Core banking systems send codes ("CSHDEP", "122", "SWIFT-OUT"), not KYRO types. A
mapping is proposed by one person and becomes ACTIVE only when someone else
approves it; until then a transaction that uses the code is refused rather than
guessed. Direction also follows from the type when nothing else gives it
(DEPOSIT is money in, WITHDRAWAL money out).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.data_foundation import TransactionCodeMap
from app.models.user import User
from app.permissions import has_permission
from app.services.audit_service import log_action

DIRECTION_BY_TYPE = {"DEPOSIT": "CREDIT", "WITHDRAWAL": "DEBIT"}


class CodeMapError(ValueError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def active_map(db: Session, source_system: str | None, source_code: str) -> TransactionCodeMap | None:
    return db.query(TransactionCodeMap).filter(
        TransactionCodeMap.source_system == (source_system or ""), TransactionCodeMap.source_code == source_code,
        TransactionCodeMap.status == "ACTIVE",
    ).first()


def resolve(db: Session, values: dict) -> dict:
    """
    Fill transaction_type, direction and channel from the source code's active mapping (values given
    explicitly win), then direction from the type. Raises CodeMapError when a code has no active mapping.
    """
    code = values.get("source_code")
    if code:
        mapping = active_map(db, values.get("source_system"), code)
        if mapping is None:
            raise CodeMapError(
                f"Transaction code {code!r} from {values.get('source_system') or 'this source'} has no approved mapping; "
                "map it in Data > Transaction codes first", 422,
            )
        values["transaction_type"] = values.get("transaction_type") or mapping.transaction_type
        values["direction"] = values.get("direction") or mapping.direction
        values["channel"] = values.get("channel") or mapping.channel
    if not values.get("direction"):
        values["direction"] = DIRECTION_BY_TYPE.get(values.get("transaction_type") or "")
    return values


def propose(db: Session, user: User, **fields) -> TransactionCodeMap:
    if db.query(TransactionCodeMap.id).filter(
        TransactionCodeMap.source_system == fields["source_system"], TransactionCodeMap.source_code == fields["source_code"],
        TransactionCodeMap.status == "PENDING",
    ).first():
        raise CodeMapError("A mapping for this code is already waiting for approval")
    row = TransactionCodeMap(**fields, status="PENDING", proposed_by=user.id)
    db.add(row)
    db.flush()
    log_action(db, entity_type="RULE_CONFIG", entity_id=row.id, action="CREATE", performed_by=user.id,
               new_values={"transaction_code_map": {k: str(v) if v is not None else None for k, v in fields.items()}})
    db.commit()
    db.refresh(row)
    return row


def decide(db: Session, user: User, map_id: uuid.UUID, approve: bool, notes: str | None) -> TransactionCodeMap:
    row = db.get(TransactionCodeMap, map_id)
    if row is None:
        raise CodeMapError("Mapping not found", 404)
    if row.status != "PENDING":
        raise CodeMapError("This mapping has already been decided")
    if row.proposed_by == user.id or not has_permission(user.role, "rules.approve"):
        raise CodeMapError("A mapping is approved by someone other than the person who proposed it", 403)
    now = datetime.now(timezone.utc)
    if approve:
        previous = active_map(db, row.source_system, row.source_code)
        if previous is not None:
            previous.status = "RETIRED"
            db.flush()  # one ACTIVE row per code (partial unique index)
        row.status = "ACTIVE"
    else:
        row.status = "REJECTED"
    row.decided_by, row.decided_at, row.decision_notes = user.id, now, notes
    log_action(db, entity_type="RULE_CONFIG", entity_id=row.id, action="APPROVE" if approve else "REJECT", performed_by=user.id,
               new_values={"transaction_code_map": f"{row.source_system}/{row.source_code}", "notes": notes})
    db.commit()
    db.refresh(row)
    return row
