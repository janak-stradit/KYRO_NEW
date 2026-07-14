"""
routers/kyc.py — Top-level KYC review triggering/listing/updating (cross-customer view).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user
from app.models.customer import Customer, KYCReview
from app.models.user import User
from app.schemas.common import Page
from app.schemas.customer import KYCReviewOut, KYCReviewUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/kyc-reviews", tags=["kyc"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=KYCReviewOut, status_code=status.HTTP_201_CREATED)
def trigger_review(
    customer_id: uuid.UUID,
    review_type: str = "ADHOC",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KYCReview:
    if db.get(Customer, customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    review = KYCReview(customer_id=customer_id, review_type=review_type, review_status="SCHEDULED")
    db.add(review)
    db.flush()
    log_action(db, entity_type="CUSTOMER", entity_id=customer_id, action="REVIEW", performed_by=user.id, new_values={"review_type": review_type})
    db.commit()
    db.refresh(review)
    return review


@router.get("", response_model=Page[KYCReviewOut])
def list_reviews(
    pagination: PaginationParams = Depends(),
    review_status: str | None = None,
    db: Session = Depends(get_db),
) -> Page[KYCReviewOut]:
    query = db.query(KYCReview)
    if review_status:
        query = query.filter(KYCReview.review_status == review_status)
    total = query.count()
    items = query.order_by(KYCReview.created_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.put("/{review_id}", response_model=KYCReviewOut)
def update_review(
    review_id: uuid.UUID, data: KYCReviewUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> KYCReview:
    review = db.get(KYCReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "KYC review not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(review, key, value)

    log_action(db, entity_type="CUSTOMER", entity_id=review.customer_id, action="UPDATE", performed_by=user.id, new_values={k: str(v) for k, v in updates.items()})
    db.commit()
    db.refresh(review)
    return review
