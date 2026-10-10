"""
visibility.py — Which records a user may see (permissions.py says what they may do).

Two rules:

1. Assignment. A role without "cases.view_all" sees only the cases assigned
   to it and the unassigned pool; a role without "customers.view_all" sees
   only customers that have such a case.
2. Sensitivity. A SAR-filed case, the documents attached to it, and the fact
   that a SAR was filed are visible only to roles with "sar.view".

A record a user may not see is reported as not found, so its existence is
not revealed.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.document import Document
from app.models.user import User
from app.permissions import has_permission

SAR_OUTCOME = "SAR_FILED"


def sees_all_cases(user: User) -> bool:
    return has_permission(user.role, "cases.view_all")


def sees_all_customers(user: User) -> bool:
    return has_permission(user.role, "customers.view_all")


def sees_sar(user: User) -> bool:
    return has_permission(user.role, "sar.view")


def alert_conditions(user: User) -> list[Any]:
    """SQL conditions that leave only the alerts this user may see."""
    conditions: list[Any] = []
    if not sees_all_cases(user):
        conditions.append(or_(Alert.assigned_to == user.id, Alert.assigned_to.is_(None)))
    if not sees_sar(user):
        conditions.append(or_(Alert.resolution_outcome.is_(None), Alert.resolution_outcome != SAR_OUTCOME))
    return conditions


def alert_visible(user: User, alert: Alert) -> bool:
    if not sees_all_cases(user) and alert.assigned_to not in (None, user.id):
        return False
    return sees_sar(user) or alert.resolution_outcome != SAR_OUTCOME


def visible_alert_or_404(db: Session, user: User, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None or not alert_visible(user, alert):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    return alert


def customer_visible(db: Session, user: User, customer_id: uuid.UUID) -> bool:
    if sees_all_customers(user):
        return True
    return db.query(Alert.id).filter(Alert.customer_id == customer_id, *alert_conditions(user)).first() is not None


def visible_customer_or_404(db: Session, user: User, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or not customer_visible(db, user, customer_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return customer


def document_visible(db: Session, user: User, document: Document) -> bool:
    """A document follows its customer, and a document attached to a SAR-filed case follows that case."""
    if not customer_visible(db, user, document.customer_id):
        return False
    if document.alert_id is None or sees_sar(user):
        return True
    alert = db.get(Alert, document.alert_id)
    return alert is None or alert.resolution_outcome != SAR_OUTCOME


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def customer_scope(resolve: Callable[[Session, dict[str, Any]], uuid.UUID | None] | None = None, *, list_allowed: bool = False):
    """
    Router dependency for customer data. Finds the customer a request is about
    (a `customer_id` in the path or query, or via `resolve` from another id in
    the path) and hides it from users who may not see it. A role limited to
    its own cases cannot list a whole collection unless `list_allowed`.
    """

    def _check(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
        if sees_all_customers(user):
            return
        customer_id = _as_uuid(request.path_params.get("customer_id") or request.query_params.get("customer_id"))
        if customer_id is None and resolve is not None:
            customer_id = resolve(db, request.path_params)
        if customer_id is not None:
            if not customer_visible(db, user, customer_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        elif request.method == "GET" and not request.path_params and not list_allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role sees customer records through its cases; ask for one customer")

    return _check
