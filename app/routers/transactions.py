"""
routers/transactions.py — Transaction ingestion (single/batch) and risk retrieval.
Newly ingested transactions are scored synchronously by the rules engine and
then by the ML models (services/auto_scoring_service.py).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import PaginationParams, get_current_user, require_permission
from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction as TransactionModel
from app.models.transaction import TransactionRiskFlag
from app.models.user import User
from app.visibility import customer_scope
from app.schemas.common import Page
from app.schemas.transaction import (
    TransactionBatchCreate,
    TransactionCreate,
    TransactionFlagOut,
    TransactionOut,
    TransactionRiskOut,
)
from app.services import auto_scoring_service
from app.services.audit_service import log_action
from app.services.rules_engine import apply_to_transaction

from app.models.transaction import Transaction as _ScopedTransaction


def _customer_of(db, path_params):
    """The customer a transaction_id in the path belongs to, for the visibility check."""
    row_id = path_params.get("transaction_id")
    try:
        row = db.get(_ScopedTransaction, uuid.UUID(str(row_id))) if row_id else None
    except ValueError:
        return None
    return row.customer_id if row else None


router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"], dependencies=[Depends(require_permission("cases.view")), Depends(customer_scope(_customer_of))])


def _get_transaction_or_404(db: Session, transaction_id: uuid.UUID) -> TransactionModel:
    txn = db.get(TransactionModel, transaction_id)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return txn


def _ingest_one(db: Session, data: TransactionCreate, performed_by: uuid.UUID | None) -> TransactionModel:
    customer = db.get(Customer, data.customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Customer {data.customer_id} not found")
    account = db.get(Account, data.account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Account {data.account_id} not found")
    if account.customer_id != customer.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Account does not belong to customer")

    txn = TransactionModel(**data.model_dump())
    db.add(txn)
    db.flush()

    _, _, alert = apply_to_transaction(db, txn, customer)
    auto_scoring_service.score_ingested(db, txn, customer, alert)

    log_action(db, entity_type="TRANSACTION", entity_id=txn.id, action="CREATE", performed_by=performed_by, new_values=data.model_dump(mode="json"))
    return txn


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create(data: TransactionCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("transactions.ingest"))) -> TransactionModel:
    txn = _ingest_one(db, data, user.id)
    db.commit()
    db.refresh(txn)
    return txn


@router.post("/batch", response_model=list[TransactionOut], status_code=status.HTTP_201_CREATED)
def create_batch(
    data: TransactionBatchCreate, db: Session = Depends(get_db), user: User = Depends(require_permission("transactions.ingest"))
) -> list[TransactionModel]:
    txns = [_ingest_one(db, item, user.id) for item in data.transactions]
    db.commit()
    for txn in txns:
        db.refresh(txn)
    return txns


@router.get("", response_model=Page[TransactionOut])
def list_transactions(
    pagination: PaginationParams = Depends(),
    customer_id: uuid.UUID | None = None,
    account_id: uuid.UUID | None = None,
    transaction_type: str | None = None,
    db: Session = Depends(get_db),
) -> Page[TransactionOut]:
    query = db.query(TransactionModel)
    if customer_id:
        query = query.filter(TransactionModel.customer_id == customer_id)
    if account_id:
        query = query.filter(TransactionModel.account_id == account_id)
    if transaction_type:
        query = query.filter(TransactionModel.transaction_type == transaction_type)
    total = query.count()
    items = query.order_by(TransactionModel.transaction_date.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> TransactionModel:
    return _get_transaction_or_404(db, transaction_id)


@router.get("/{transaction_id}/risk", response_model=TransactionRiskOut)
def get_risk(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> TransactionRiskOut:
    txn = _get_transaction_or_404(db, transaction_id)
    triggered = (txn.risk_flags or {}).get("triggered_rules", [])
    return TransactionRiskOut(transaction_id=txn.id, risk_score=txn.risk_score, risk_flags=txn.risk_flags, triggered_rules=triggered)


@router.get("/{transaction_id}/flags", response_model=list[TransactionFlagOut])
def get_flags(transaction_id: uuid.UUID, db: Session = Depends(get_db)) -> list[TransactionRiskFlag]:
    _get_transaction_or_404(db, transaction_id)
    return db.query(TransactionRiskFlag).filter(TransactionRiskFlag.transaction_id == transaction_id).all()
