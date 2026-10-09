"""
routers/beneficial_owners.py — UBO capture, verification, and CDD-completeness
summary for CORPORATE/FUND customers (Phase 4.5).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_permission
from app.models.beneficial_ownership import BeneficialOwner
from app.models.customer import Customer
from app.models.user import User
from app.schemas.beneficial_ownership import (
    BeneficialOwnerCreate,
    BeneficialOwnerOut,
    BeneficialOwnerUpdate,
    BeneficialOwnerVerify,
    UBOSummaryOut,
)
from app.services import beneficial_ownership_service as ubo_service

router = APIRouter(
    prefix="/api/v1/customers/{customer_id}/beneficial-owners",
    tags=["beneficial-owners"],
    dependencies=[Depends(require_permission("cases.view"))],
)


def _get_customer_or_404(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


def _get_owner_or_404(db: Session, customer_id: uuid.UUID, owner_id: uuid.UUID) -> BeneficialOwner:
    owner = db.get(BeneficialOwner, owner_id)
    if owner is None or owner.customer_id != customer_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Beneficial owner not found")
    return owner


# Registered before the "/{owner_id}..." routes so "summary" is never
# mistaken for an owner_id path parameter.
@router.get("/summary", response_model=UBOSummaryOut)
def get_summary(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    _get_customer_or_404(db, customer_id)
    return ubo_service.get_ubo_summary(db, customer_id)


@router.post("", response_model=BeneficialOwnerOut, status_code=status.HTTP_201_CREATED)
def create(
    customer_id: uuid.UUID,
    data: BeneficialOwnerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("customers.edit")),
) -> BeneficialOwner:
    customer = _get_customer_or_404(db, customer_id)
    try:
        return ubo_service.create_beneficial_owner(db, customer, data, performed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.get("", response_model=list[BeneficialOwnerOut])
def list_owners(
    customer_id: uuid.UUID,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[BeneficialOwner]:
    _get_customer_or_404(db, customer_id)
    query = db.query(BeneficialOwner).filter(BeneficialOwner.customer_id == customer_id)
    if not include_inactive:
        query = query.filter(BeneficialOwner.effective_to.is_(None))
    return query.order_by(BeneficialOwner.created_at.desc()).all()


@router.put("/{owner_id}", response_model=BeneficialOwnerOut)
def update(
    customer_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: BeneficialOwnerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("customers.edit")),
) -> BeneficialOwner:
    owner = _get_owner_or_404(db, customer_id, owner_id)
    try:
        return ubo_service.update_beneficial_owner(db, owner, data, performed_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/{owner_id}/verify", response_model=BeneficialOwnerOut)
def verify(
    customer_id: uuid.UUID,
    owner_id: uuid.UUID,
    data: BeneficialOwnerVerify,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("ubo.verify")),
) -> BeneficialOwner:
    owner = _get_owner_or_404(db, customer_id, owner_id)
    return ubo_service.verify_beneficial_owner(db, owner, data, performed_by=user.id)


@router.post("/{owner_id}/deactivate", response_model=BeneficialOwnerOut)
def deactivate(
    customer_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("customers.edit")),
) -> BeneficialOwner:
    owner = _get_owner_or_404(db, customer_id, owner_id)
    return ubo_service.deactivate_beneficial_owner(db, owner, performed_by=user.id)
