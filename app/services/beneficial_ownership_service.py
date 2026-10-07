"""
services/beneficial_ownership_service.py — UBO CRUD, verification workflow,
and CDD-completeness summary for CORPORATE/FUND customers (Phase 4.5).

Beneficial owner changes are audit-logged against the *owning customer's*
entity_id (entity_type="CUSTOMER") rather than adding a new AuditLog
entity_type — UBO data is part of that customer's CDD file, the same way
create_kyc_review() already logs KYC reviews under the customer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer
from app.schemas.beneficial_ownership import BeneficialOwnerCreate, BeneficialOwnerUpdate, BeneficialOwnerVerify
from app.services.audit_service import log_action
from app.services.screening_service import screen_beneficial_owner

UBO_ELIGIBLE_CUSTOMER_TYPES = ("CORPORATE", "FUND")


def _validate_ownership_total(
    db: Session,
    customer_id: uuid.UUID,
    control_type: str,
    new_percentage: float | None,
    *,
    exclude_owner_id: uuid.UUID | None = None,
) -> None:
    if control_type != "OWNERSHIP" or new_percentage is None:
        return
    query = db.query(func.sum(BeneficialOwner.ownership_percentage)).filter(
        BeneficialOwner.customer_id == customer_id,
        BeneficialOwner.control_type == "OWNERSHIP",
        BeneficialOwner.effective_to.is_(None),
    )
    if exclude_owner_id is not None:
        query = query.filter(BeneficialOwner.id != exclude_owner_id)
    existing_total = float(query.scalar() or 0)
    if existing_total + float(new_percentage) > 100:
        raise ValueError(
            f"Total disclosed ownership would exceed 100% ({existing_total}% already recorded for this customer)"
        )


def create_beneficial_owner(
    db: Session, customer: Customer, data: BeneficialOwnerCreate, performed_by: uuid.UUID | None = None
) -> BeneficialOwner:
    if customer.customer_type not in UBO_ELIGIBLE_CUSTOMER_TYPES:
        raise ValueError("Beneficial owners can only be recorded for CORPORATE or FUND customers")

    _validate_ownership_total(db, customer.id, data.control_type, data.ownership_percentage)

    owner = BeneficialOwner(customer_id=customer.id, **data.model_dump())
    db.add(owner)
    db.flush()

    screen_beneficial_owner(db, owner, triggered_by="SYSTEM")

    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=customer.id,
        action="CREATE",
        performed_by=performed_by,
        new_values={"beneficial_owner_id": str(owner.id), **data.model_dump(mode="json")},
    )
    db.commit()
    db.refresh(owner)
    return owner


def update_beneficial_owner(
    db: Session, owner: BeneficialOwner, data: BeneficialOwnerUpdate, performed_by: uuid.UUID | None = None
) -> BeneficialOwner:
    updates = data.model_dump(exclude_unset=True)
    old_values = {k: getattr(owner, k) for k in updates}

    if "ownership_percentage" in updates or "control_type" in updates:
        _validate_ownership_total(
            db,
            owner.customer_id,
            updates.get("control_type", owner.control_type),
            updates.get("ownership_percentage", owner.ownership_percentage),
            exclude_owner_id=owner.id,
        )

    rescreen_needed = "full_name" in updates or "date_of_birth" in updates

    for key, value in updates.items():
        setattr(owner, key, value)
    db.flush()

    if rescreen_needed:
        screen_beneficial_owner(db, owner, triggered_by="SYSTEM")

    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=owner.customer_id,
        action="UPDATE",
        performed_by=performed_by,
        old_values={"beneficial_owner_id": str(owner.id), **{k: str(v) for k, v in old_values.items()}},
        new_values={"beneficial_owner_id": str(owner.id), **{k: str(v) for k, v in updates.items()}},
    )
    db.commit()
    db.refresh(owner)
    return owner


def verify_beneficial_owner(
    db: Session, owner: BeneficialOwner, data: BeneficialOwnerVerify, performed_by: uuid.UUID | None = None
) -> BeneficialOwner:
    owner.verification_status = data.verification_status
    owner.verified_at = datetime.now(timezone.utc)
    owner.verified_by = performed_by
    db.flush()

    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=owner.customer_id,
        action="APPROVE" if data.verification_status == "VERIFIED" else "REJECT",
        performed_by=performed_by,
        new_values={
            "beneficial_owner_id": str(owner.id),
            "verification_status": data.verification_status,
            "notes": data.notes,
        },
    )
    db.commit()
    db.refresh(owner)
    return owner


def deactivate_beneficial_owner(
    db: Session, owner: BeneficialOwner, performed_by: uuid.UUID | None = None
) -> BeneficialOwner:
    """Ends the ownership record as of today rather than deleting it, so the
    CDD file keeps a full history of who owned/controlled the entity when."""
    owner.effective_to = date.today()
    db.flush()

    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=owner.customer_id,
        action="DELETE",
        performed_by=performed_by,
        old_values={"beneficial_owner_id": str(owner.id)},
    )
    db.commit()
    db.refresh(owner)
    return owner


def get_ubo_summary(db: Session, customer_id: uuid.UUID) -> dict:
    owners = (
        db.query(BeneficialOwner)
        .filter(BeneficialOwner.customer_id == customer_id, BeneficialOwner.effective_to.is_(None))
        .all()
    )
    total_pct = sum(
        float(o.ownership_percentage)
        for o in owners
        if o.control_type == "OWNERSHIP" and o.ownership_percentage is not None
    )
    verified = sum(1 for o in owners if o.verification_status == "VERIFIED")
    pending = sum(1 for o in owners if o.verification_status == "PENDING")
    rejected = sum(1 for o in owners if o.verification_status == "REJECTED")
    sanctioned = sum(1 for o in owners if o.sanctions_flag)

    return {
        "customer_id": customer_id,
        "owner_count": len(owners),
        "total_ownership_percentage": round(total_pct, 2),
        "verified_count": verified,
        "pending_count": pending,
        "rejected_count": rejected,
        "sanctioned_count": sanctioned,
        "is_cdd_complete": len(owners) > 0 and pending == 0 and sanctioned == 0,
    }
