"""
routers/customers.py — Customer CRUD, risk profile, KYC reviews, and screening.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user
from app.models.customer import CustomerRiskProfile, KYCReview, PEPSanctionsScreening
from app.models.customer import Customer as CustomerModel
from app.models.user import User
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    KYCReviewCreate,
    KYCReviewOut,
    RiskProfileOut,
    ScreeningOut,
)
from app.services.audit_service import log_action
from app.services.customer_service import create_customer, update_customer

router = APIRouter(prefix="/api/v1/customers", tags=["customers"], dependencies=[Depends(get_current_user)])


def _get_customer_or_404(db: Session, customer_id: uuid.UUID) -> CustomerModel:
    customer = db.get(CustomerModel, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create(data: CustomerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> CustomerModel:
    return create_customer(db, data, performed_by=user.id)


@router.get("", response_model=Page[CustomerOut])
def list_customers(
    pagination: PaginationParams = Depends(),
    kyc_status: str | None = None,
    risk_level: str | None = None,
    db: Session = Depends(get_db),
) -> Page[CustomerOut]:
    query = db.query(CustomerModel)
    if kyc_status:
        query = query.filter(CustomerModel.kyc_status == kyc_status)
    if risk_level:
        query = query.filter(CustomerModel.risk_level == risk_level)
    total = query.count()
    items = query.order_by(CustomerModel.created_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> CustomerModel:
    return _get_customer_or_404(db, customer_id)


@router.put("/{customer_id}", response_model=CustomerOut)
def update(
    customer_id: uuid.UUID, data: CustomerUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> CustomerModel:
    customer = _get_customer_or_404(db, customer_id)
    return update_customer(db, customer, data, performed_by=user.id)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete(customer_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    customer = _get_customer_or_404(db, customer_id)
    customer.kyc_status = "REJECTED"
    log_action(db, entity_type="CUSTOMER", entity_id=customer.id, action="DELETE", performed_by=user.id)
    db.commit()


@router.get("/{customer_id}/risk-profile", response_model=list[RiskProfileOut])
def get_risk_profile(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> list[CustomerRiskProfile]:
    _get_customer_or_404(db, customer_id)
    return db.query(CustomerRiskProfile).filter(CustomerRiskProfile.customer_id == customer_id).all()


@router.get("/{customer_id}/kyc-reviews", response_model=list[KYCReviewOut])
def list_kyc_reviews(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> list[KYCReview]:
    _get_customer_or_404(db, customer_id)
    return db.query(KYCReview).filter(KYCReview.customer_id == customer_id).order_by(KYCReview.created_at.desc()).all()


@router.post("/{customer_id}/kyc-reviews", response_model=KYCReviewOut, status_code=status.HTTP_201_CREATED)
def create_kyc_review(
    customer_id: uuid.UUID, data: KYCReviewCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> KYCReview:
    _get_customer_or_404(db, customer_id)
    review = KYCReview(customer_id=customer_id, **data.model_dump())
    db.add(review)
    db.flush()
    log_action(db, entity_type="CUSTOMER", entity_id=customer_id, action="REVIEW", performed_by=user.id, new_values=data.model_dump(mode="json"))
    db.commit()
    db.refresh(review)
    return review


@router.get("/{customer_id}/screening", response_model=list[ScreeningOut])
def get_screening(customer_id: uuid.UUID, db: Session = Depends(get_db)) -> list[PEPSanctionsScreening]:
    _get_customer_or_404(db, customer_id)
    return (
        db.query(PEPSanctionsScreening)
        .filter(PEPSanctionsScreening.customer_id == customer_id)
        .order_by(PEPSanctionsScreening.screened_at.desc())
        .all()
    )
