"""
services/customer_service.py — Customer CRUD with audit logging.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.services.audit_service import log_action
from app.services.screening_service import screen_customer

_SCREENING_TRIGGER_FIELDS = {"full_name", "date_of_birth", "country", "residency_country"}


# A first segment from the customer type; KYC refines it (e.g. HNW, SME, MSB) at onboarding or review
_SEGMENT_BY_TYPE = {"INDIVIDUAL": "RETAIL", "CORPORATE": "CORPORATE", "FUND": "FUND"}


def create_customer(db: Session, data: CustomerCreate, performed_by: uuid.UUID | None = None) -> Customer:
    customer = Customer(**data.model_dump())
    if customer.segment is None:
        customer.segment = _SEGMENT_BY_TYPE.get(customer.customer_type or "")
    db.add(customer)
    db.flush()
    screen_customer(db, customer, triggered_by="SYSTEM")
    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=customer.id,
        action="CREATE",
        performed_by=performed_by,
        new_values=data.model_dump(mode="json"),
    )
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session, customer: Customer, data: CustomerUpdate, performed_by: uuid.UUID | None = None
) -> Customer:
    updates = data.model_dump(exclude_unset=True)
    old_values = {k: getattr(customer, k) for k in updates}
    for key, value in updates.items():
        setattr(customer, key, value)
    db.flush()
    if _SCREENING_TRIGGER_FIELDS & updates.keys():
        screen_customer(db, customer, triggered_by="SYSTEM")
    log_action(
        db,
        entity_type="CUSTOMER",
        entity_id=customer.id,
        action="UPDATE",
        performed_by=performed_by,
        old_values={k: str(v) for k, v in old_values.items()},
        new_values={k: str(v) for k, v in updates.items()},
    )
    db.commit()
    db.refresh(customer)
    return customer
