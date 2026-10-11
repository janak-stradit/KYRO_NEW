"""
tests/api/test_patterns.py — Behavioural patterns measured against each
customer's own baseline (the last 30 days against the 90 days before).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.account import Account
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.services import pattern_service

pytestmark = pytest.mark.db

NOW = datetime.now(timezone.utc)


def days_ago(n: float) -> datetime:
    return NOW - timedelta(days=n)


def midday(n: int) -> datetime:
    """Noon n days ago, so a burst of same-day transactions cannot straddle midnight."""
    return (NOW - timedelta(days=n)).replace(hour=12, minute=0, second=0, microsecond=0)


class Book:
    """Builds one customer's transactions for a test."""

    def __init__(self, db, name: str):
        self.db = db
        self.customer = Customer(full_name=name, email=f"{name.lower().replace(' ', '.')}@patterns.example", customer_type="INDIVIDUAL")
        db.add(self.customer)
        db.flush()
        self.account = Account(customer_id=self.customer.id, account_type="CHECKING", balance=0)
        db.add(self.account)
        db.flush()

    def txn(self, when, amount=100, currency="USD", counterparty="Regular Payee", country="GB", kind="TRANSFER"):
        self.db.add(Transaction(
            customer_id=self.customer.id, account_id=self.account.id, transaction_date=when, amount=amount, currency=currency,
            meta_counterparty=counterparty, meta_country=country, transaction_type=kind,
        ))
        return self

    def steady_baseline(self, n=8, **kwargs):
        """n unremarkable transactions spread over the baseline period."""
        for i in range(n):
            self.txn(days_ago(40 + i * 9), **kwargs)
        return self


def findings(db, book) -> dict[str, dict]:
    db.commit()
    rows = pattern_service.pattern_activity(db)["customer_rows"]
    return {r["pattern"]: r for r in rows if r["customer_id"] == book.customer.id}


def test_steady_customer_is_not_flagged(db_session):
    book = Book(db_session, "Steady Sam").steady_baseline()
    book.txn(days_ago(5)).txn(days_ago(3), amount=150)
    assert findings(db_session, book) == {}


def test_unusual_amount_is_judged_per_currency_against_previous_largest(db_session):
    book = Book(db_session, "Amount Amy").steady_baseline(amount=1000)
    book.txn(days_ago(4), amount=1900)   # under double the previous largest
    book.txn(days_ago(3), amount=5000)   # more than double
    book.txn(days_ago(2), amount=900000, currency="JPY")  # no JPY baseline, so not judged
    found = findings(db_session, book)
    assert set(found) == {"THRESHOLD_BREACH"}
    assert found["THRESHOLD_BREACH"]["hits"] == 1
    assert found["THRESHOLD_BREACH"]["evidence"] == "5,000.00 USD against a previous largest of 1,000.00 USD"


def test_velocity_spike_needs_a_busy_day_well_above_usual(db_session):
    book = Book(db_session, "Velocity Vic").steady_baseline()
    for i in range(5):
        book.txn(midday(2) + timedelta(minutes=i * 7))
    book.txn(midday(6)).txn(midday(6) + timedelta(minutes=5))  # two in a day is not a spike
    found = findings(db_session, book)
    assert set(found) == {"VELOCITY_SPIKE"}
    assert found["VELOCITY_SPIKE"]["hits"] == 1 and "5 transactions on" in found["VELOCITY_SPIKE"]["evidence"]


def test_customer_who_is_always_busy_is_not_a_velocity_spike(db_session):
    book = Book(db_session, "Busy Bea")
    for day in (40, 50, 60, 70):
        for i in range(5):
            book.txn(midday(day) + timedelta(minutes=i))
    for i in range(5):
        book.txn(midday(3) + timedelta(minutes=i))
    assert "VELOCITY_SPIKE" not in findings(db_session, book)


def test_first_high_risk_country_is_a_geographic_shift(db_session):
    book = Book(db_session, "Geo Gina").steady_baseline()
    book.txn(days_ago(3), country="SYRIA").txn(days_ago(2), country="FR")  # one ordinary new country is not a shift
    found = findings(db_session, book)
    assert set(found) == {"GEOGRAPHIC_SHIFT"}
    assert found["GEOGRAPHIC_SHIFT"]["evidence"] == "first dealings with a high-risk jurisdiction: SYRIA"

    veteran = Book(db_session, "Geo Gus").steady_baseline(country="SYRIA")
    veteran.txn(days_ago(3), country="SYRIA")
    assert findings(db_session, veteran) == {}  # already dealt with it before: not a change


def test_jump_in_new_countries_and_counterparties_is_flagged(db_session):
    book = Book(db_session, "Change Chen").steady_baseline()
    for i, (country, payee) in enumerate([("FR", "Payee A"), ("DE", "Payee B"), ("ES", "Payee C"), ("IT", "Payee D")]):
        book.txn(days_ago(5 - i), country=country, counterparty=payee)
    found = findings(db_session, book)
    assert set(found) == {"GEOGRAPHIC_SHIFT", "COUNTERPARTY_CHANGES"}
    assert found["COUNTERPARTY_CHANGES"]["hits"] == 4
    assert found["COUNTERPARTY_CHANGES"]["evidence"] == "100% of transactions to new counterparties, up from 12%"
    assert "new to the customer" in found["GEOGRAPHIC_SHIFT"]["evidence"]


def test_customer_who_always_uses_new_counterparties_is_not_flagged(db_session):
    book = Book(db_session, "Varied Val")
    for i in range(8):
        book.txn(days_ago(40 + i * 9), counterparty=f"Old Payee {i}", country=f"C{i}")
    for i in range(4):
        book.txn(days_ago(5 - i), counterparty=f"New Payee {i}", country=f"N{i}")
    assert findings(db_session, book) == {}


def test_new_transaction_type(db_session):
    book = Book(db_session, "Type Tom").steady_baseline(kind="DEPOSIT")
    book.txn(days_ago(3), kind="FX").txn(days_ago(2), kind="DEPOSIT")
    found = findings(db_session, book)
    assert set(found) == {"COMPLEXITY_SHIFT"} and found["COMPLEXITY_SHIFT"]["evidence"] == "first use of fx"


def test_reactivation_after_a_long_silence(db_session):
    book = Book(db_session, "Dormant Dee")
    for day in (200, 190, 180):
        book.txn(days_ago(day))
    book.txn(days_ago(4)).txn(days_ago(2))
    found = findings(db_session, book)
    assert set(found) == {"INACTIVE_REACTIVATION"}
    assert found["INACTIVE_REACTIVATION"]["hits"] == 2 and "days with none" in found["INACTIVE_REACTIVATION"]["evidence"]

    newcomer = Book(db_session, "New Ned")
    newcomer.txn(days_ago(4)).txn(days_ago(2))
    assert findings(db_session, newcomer) == {}  # a new customer is not a reactivation


def test_customer_without_a_baseline_is_not_judged(db_session):
    book = Book(db_session, "Thin Theo")
    book.txn(days_ago(50)).txn(days_ago(45))  # too little history
    book.txn(days_ago(3), amount=999999, country="SYRIA", kind="FX", counterparty="Someone New")
    assert findings(db_session, book) == {}


def test_endpoints_report_totals_and_evidence(client, auth_headers, db_session):
    before = client.get("/api/v1/dashboard/patterns", headers=auth_headers).json()
    book = Book(db_session, "Endpoint Eve").steady_baseline(amount=1000)
    book.txn(days_ago(3), amount=5000)
    db_session.commit()

    after = client.get("/api/v1/dashboard/patterns", headers=auth_headers).json()
    amount = lambda body: next(p for p in body["patterns"] if p["id"] == "THRESHOLD_BREACH")  # noqa: E731
    assert amount(after)["hit_count"] == amount(before)["hit_count"] + 1
    assert amount(after)["customers"] == amount(before)["customers"] + 1
    assert (after["window_days"], after["baseline_days"]) == (30, 90)
    assert after["customers_affected"] == before["customers_affected"] + 1
    assert {p["id"] for p in after["patterns"]} == {p["id"] for p in pattern_service.PATTERNS}

    rows = client.get("/api/v1/dashboard/patterns/customers", params={"q": "Endpoint Eve"}, headers=auth_headers).json()
    assert rows["total"] == 1
    row = rows["items"][0]
    assert (row["pattern"], row["pattern_label"], row["hits"]) == ("THRESHOLD_BREACH", "Unusual Amount", 1)
    assert "previous largest" in row["evidence"]
    assert client.get("/api/v1/dashboard/patterns/customers", params={"q": "Endpoint Eve", "pattern": "VELOCITY_SPIKE"}, headers=auth_headers).json()["total"] == 0
