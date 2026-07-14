"""
routers/accounts.py — Account CRUD, transaction listing, and balance history.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user
from app.models.account import Account as AccountModel
from app.models.account import AccountBalance
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.account import AccountBalanceOut, AccountCreate, AccountOut, AccountStatusUpdate
from app.schemas.common import Page
from app.schemas.transaction import TransactionOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"], dependencies=[Depends(get_current_user)])


def _get_account_or_404(db: Session, account_id: uuid.UUID) -> AccountModel:
    account = db.get(AccountModel, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create(data: AccountCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AccountModel:
    if db.get(Customer, data.customer_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")

    account = AccountModel(**data.model_dump())
    db.add(account)
    db.flush()
    log_action(db, entity_type="ACCOUNT", entity_id=account.id, action="CREATE", performed_by=user.id, new_values=data.model_dump(mode="json"))
    db.commit()
    db.refresh(account)
    return account


@router.get("", response_model=Page[AccountOut])
def list_accounts(
    pagination: PaginationParams = Depends(),
    customer_id: uuid.UUID | None = None,
    account_status: str | None = None,
    db: Session = Depends(get_db),
) -> Page[AccountOut]:
    query = db.query(AccountModel)
    if customer_id:
        query = query.filter(AccountModel.customer_id == customer_id)
    if account_status:
        query = query.filter(AccountModel.account_status == account_status)
    total = query.count()
    items = query.order_by(AccountModel.created_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: uuid.UUID, db: Session = Depends(get_db)) -> AccountModel:
    return _get_account_or_404(db, account_id)


@router.get("/{account_id}/transactions", response_model=Page[TransactionOut])
def get_account_transactions(
    account_id: uuid.UUID, pagination: PaginationParams = Depends(), db: Session = Depends(get_db)
) -> Page[TransactionOut]:
    _get_account_or_404(db, account_id)
    query = db.query(Transaction).filter(Transaction.account_id == account_id)
    total = query.count()
    items = query.order_by(Transaction.transaction_date.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{account_id}/balance-history", response_model=list[AccountBalanceOut])
def get_balance_history(account_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AccountBalance]:
    _get_account_or_404(db, account_id)
    return (
        db.query(AccountBalance)
        .filter(AccountBalance.account_id == account_id)
        .order_by(AccountBalance.recorded_at.desc())
        .all()
    )


@router.put("/{account_id}/status", response_model=AccountOut)
def update_status(
    account_id: uuid.UUID, data: AccountStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AccountModel:
    account = _get_account_or_404(db, account_id)
    old_status = account.account_status
    account.account_status = data.account_status
    log_action(
        db,
        entity_type="ACCOUNT",
        entity_id=account.id,
        action="UPDATE",
        performed_by=user.id,
        old_values={"account_status": old_status},
        new_values={"account_status": data.account_status},
    )
    db.commit()
    db.refresh(account)
    return account
