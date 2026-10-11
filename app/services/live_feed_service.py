"""
services/live_feed_service.py — A live feed of synthetic transactions that is
started and stopped from the Data Feeds page.

While it runs, a background thread records a made-up transaction for a random
existing account every few seconds. Each one goes through the same code path
as a transaction posted to the API, so the rules engine and the ML models
score it, alerts are opened and it is audited. Every row is marked source_system="synthetic_feed"
so it can be told apart from client data.

The feed is off unless SYNTHETIC_FEED_ENABLED=true: it must never run against
a database that holds real customers. Its state lives in this process, so it
assumes the API runs as a single process (as it does locally and in Docker).
"""
from __future__ import annotations

import logging
import random
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import app.database as database
from app.config import get_settings
from app.models.account import Account
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.ml_score import MLScore
from app.schemas.transaction import TransactionCreate
from app.services import auto_scoring_service
from app.services.rules_engine import HIGH_RISK_COUNTRIES

logger = logging.getLogger("kyro.live_feed")

SOURCE = "synthetic_feed"
DEFAULT_PER_MINUTE = 12
MAX_PER_MINUTE = 120
MAX_RUN_SECONDS = 60 * 60  # a forgotten feed stops itself
_MAX_FAILURES = 5  # in a row, before the feed gives up
_RECENT_KEPT = 15

_COUNTRIES = ["US", "GB", "DE", "FR", "IN", "CN", "JP", "AU", "CA", "BR", "SG", "AE", "CH", "NL", "SE", "IT", "ES", "KR", "MX", "ZA"]
_TXN_TYPES = ["DEPOSIT", "WITHDRAWAL", "TRANSFER", "FX", "TRADE"]
_COUNTERPARTY_TYPES = ["INDIVIDUAL", "CORPORATE", "FINANCIAL_INSTITUTION"]
_COUNTERPARTIES = [
    "Northwind Trading Ltd", "Meridian Logistics", "Blue Harbor Capital", "Atlas Commodities", "Silverline Exports",
    "Oakfield Holdings", "Pacific Rim Partners", "Crestview Advisors", "Redwood Supplies", "Summit Freight GmbH",
    "Lumen Payments", "Vertex Industrial", "Harborlight Shipping", "Evergreen Metals", "Kestrel Consulting",
]


class LiveFeedError(RuntimeError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class _State:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.per_minute = DEFAULT_PER_MINUTE
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = None
        self.started_by: str | None = None
        self.transactions = 0
        self.flagged = 0
        self.alerts = 0
        self.anomalies = 0
        self.last_error: str | None = None
        self.recent: deque[dict[str, Any]] = deque(maxlen=_RECENT_KEPT)

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive() and not self.stop.is_set()


_lock = threading.Lock()
_state = _State()


def _amount(rng: Any = random) -> float:
    # Mostly everyday amounts, with a tail large enough to trip the rules
    r = rng.random()
    if r < 0.60:
        return round(rng.uniform(10, 800), 2)
    if r < 0.85:
        return round(rng.uniform(800, 8000), 2)
    if r < 0.96:
        return round(rng.uniform(8000, 25000), 2)
    return round(rng.uniform(25000, 150000), 2)


def _country(home: str | None, rng: Any = random) -> str:
    r = rng.random()
    if r < 0.04:
        return rng.choice(sorted(HIGH_RISK_COUNTRIES))
    if r < 0.70 and home:
        return home
    return rng.choice(_COUNTRIES)


def generate_one(db: Session, user_id: uuid.UUID | None) -> dict[str, Any]:
    """Record one synthetic transaction for a random active account. The caller commits."""
    from app.routers.transactions import _ingest_one  # rules engine, ML scoring, flags, alerts, audit

    account = db.query(Account).filter(Account.account_status == "ACTIVE").order_by(func.random()).first()
    if account is None:
        raise LiveFeedError("There are no active accounts to send transactions for. Load customers and accounts first.")
    customer = db.get(Customer, account.customer_id)
    country = _country(customer.country)
    payload = TransactionCreate(
        customer_id=customer.id,
        account_id=account.id,
        transaction_date=datetime.now(timezone.utc),
        transaction_type=random.choice(_TXN_TYPES),
        amount=_amount(),
        currency=account.currency,
        meta_counterparty=random.choice(_COUNTERPARTIES),
        meta_counterparty_type=random.choice(_COUNTERPARTY_TYPES),
        meta_country=country,
        meta_destination_country=country,
        meta_origin_country=customer.country,
        meta_source=SOURCE,
        source_system=SOURCE,
    )
    alerts_before = db.query(func.count(Alert.id)).filter(Alert.customer_id == customer.id).scalar()
    txn = _ingest_one(db, payload, user_id)
    alerts_after = db.query(func.count(Alert.id)).filter(Alert.customer_id == customer.id).scalar()
    ml = db.query(MLScore).filter(MLScore.transaction_id == txn.id).order_by(MLScore.created_at.desc()).first()
    return {
        "id": str(txn.id),
        "at": payload.transaction_date.isoformat(),
        "customer_id": str(customer.id),
        "customer": customer.full_name,
        "transaction_type": payload.transaction_type,
        "amount": payload.amount,
        "currency": payload.currency,
        "country": country,
        "risk_score": txn.risk_score,
        "triggered_rules": (txn.risk_flags or {}).get("triggered_rules", []),
        "alert_opened": alerts_after > alerts_before,
        "ai_score": round(ml.combined_score, 1) if ml else None,
        "anomaly": bool(ml and ml.anomaly_flag),
    }


def _loop(state: _State, user_id: uuid.UUID | None) -> None:
    interval = 60.0 / state.per_minute
    failures = 0
    started = datetime.now(timezone.utc)
    while True:
        try:
            with database.SessionLocal() as db:
                row = generate_one(db, user_id)
                db.commit()
            failures = 0
            state.transactions += 1
            state.flagged += bool(row["triggered_rules"])
            state.alerts += row["alert_opened"]
            state.anomalies += row["anomaly"]
            state.recent.appendleft(row)
        except LiveFeedError as exc:
            state.last_error = str(exc)
            break
        except Exception as exc:  # keep the feed alive through a failed row
            failures += 1
            logger.exception("Synthetic feed could not record a transaction")
            state.last_error = f"A transaction could not be recorded: {exc}"[:300]
            if failures >= _MAX_FAILURES:
                break
        if (datetime.now(timezone.utc) - started).total_seconds() >= MAX_RUN_SECONDS:
            state.last_error = f"Stopped by itself after {MAX_RUN_SECONDS // 60} minutes."
            break
        if state.stop.wait(interval):
            return  # stopped by a user; stop() records the time
    state.stop.set()
    state.stopped_at = datetime.now(timezone.utc)


def status() -> dict[str, Any]:
    state = _state
    return {
        "enabled": get_settings().synthetic_feed_enabled,
        "running": state.running,
        "per_minute": state.per_minute,
        "started_at": state.started_at,
        "stopped_at": None if state.running else state.stopped_at,
        "started_by": state.started_by,
        "transactions": state.transactions,
        "flagged": state.flagged,
        "alerts": state.alerts,
        "anomalies": state.anomalies,
        "ai_unavailable": auto_scoring_service.unavailable_reason(),
        "last_error": state.last_error,
        "recent": list(state.recent),
    }


def start(db: Session, *, per_minute: int, user_id: uuid.UUID | None, username: str | None) -> dict[str, Any]:
    """Start the feed. Starting a feed that is already running leaves it as it is."""
    global _state
    if not get_settings().synthetic_feed_enabled:
        raise LiveFeedError("The synthetic feed is turned off on this system (SYNTHETIC_FEED_ENABLED).", 403)
    if not db.query(Account.id).filter(Account.account_status == "ACTIVE").first():
        raise LiveFeedError("There are no active accounts to send transactions for. Load customers and accounts first.")
    with _lock:
        if not _state.running:
            state = _State()
            state.per_minute = max(1, min(MAX_PER_MINUTE, per_minute))
            state.started_at = datetime.now(timezone.utc)
            state.started_by = username
            state.thread = threading.Thread(target=_loop, args=(state, user_id), name="kyro-synthetic-feed", daemon=True)
            _state = state
            state.thread.start()
    return status()


def stop() -> dict[str, Any]:
    with _lock:
        state = _state
        if state.running:
            state.stop.set()
            state.stopped_at = datetime.now(timezone.utc)
            state.thread.join(timeout=10)  # let the row in progress finish
    return status()
